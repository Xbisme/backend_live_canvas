"""The async media pipeline (BE-004, Constitution VII; spec FR-009/FR-010).

One task carries a wallpaper from ``processing`` to ``published`` or ``failed``:

    sniff (range-GET magic bytes) → size guard → download staging → probe →
    normalize master → thumbnail → watermarked preview → upload artifacts →
    ONE atomic DB write → delete staging

Idempotent: an already-published wallpaper is a no-op; a retry after failure starts
over from the (still present) staging object. A failure in any step records a
``failure_reason`` and never leaves a half-published row — the single atomic UPDATE
at the end is the only transition to ``published``.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.uploads import ffmpeg, storage

logger = logging.getLogger(__name__)

ACCEPTED_VIDEO_MIMES = {"video/mp4", "video/quicktime"}


class PipelineReject(Exception):
    """Terminal validation failure — goes straight to status=failed (no retry)."""


def _sniff_video(key: str) -> None:
    import magic  # deferred: needs system libmagic

    head = storage.read_head(key)
    mime = magic.from_buffer(head, mime=True)
    if mime not in ACCEPTED_VIDEO_MIMES:
        raise PipelineReject(f"not an accepted video (sniffed {mime})")


def _size_guard(key: str) -> None:
    size = storage.head_size(key)
    if size is None:
        raise PipelineReject("staged object is missing")
    if size > settings.UPLOAD_MAX_BYTES:
        raise PipelineReject(
            f"file is {size} bytes — exceeds the {settings.UPLOAD_MAX_BYTES} byte ceiling"
        )


@shared_task(bind=True, max_retries=3)
def process_wallpaper(self, wallpaper_id: int) -> str:
    from apps.wallpapers.models import Wallpaper, WallpaperStatus

    try:
        wallpaper = Wallpaper.objects.get(pk=wallpaper_id)
    except Wallpaper.DoesNotExist:
        logger.warning("process_wallpaper: wallpaper %s vanished", wallpaper_id)
        return "missing"

    # Idempotency guard (FR-010): a wallpaper with a master already has self-hosted
    # media — re-delivery is a no-op. Keyed on master_key, NOT on status: seeded items
    # enter the backfill as published-with-interim-URLs and MUST still be processed.
    if wallpaper.master_key:
        return "already-processed"
    staging_key = wallpaper.staging_key
    if not staging_key:
        _fail(wallpaper, "no staging object recorded")
        return "failed"

    try:
        _size_guard(staging_key)
        _sniff_video(staging_key)

        with tempfile.TemporaryDirectory(prefix="lc-pipeline-") as tmp:
            tmpdir = Path(tmp)
            src = tmpdir / "source"
            storage.download_file(staging_key, src)

            meta = ffmpeg.probe(src)

            master = tmpdir / "master.mp4"
            thumb = tmpdir / "thumb.jpg"
            preview = tmpdir / "preview.mp4"
            ffmpeg.normalize_master(src, master)
            ffmpeg.extract_thumbnail(src, thumb)
            ffmpeg.render_preview(src, preview)

            master_key = storage.new_key(storage.MASTERS_PREFIX, "mp4")
            thumb_key = storage.new_key(storage.THUMBS_PREFIX, "jpg")
            preview_key = storage.new_key(storage.PREVIEWS_PREFIX, "mp4")
            storage.upload_file(master, master_key, zone=storage.PRIVATE, content_type="video/mp4")
            storage.upload_file(thumb, thumb_key, zone=storage.PUBLIC, content_type="image/jpeg")
            storage.upload_file(preview, preview_key, zone=storage.PUBLIC, content_type="video/mp4")
            master_size = master.stat().st_size
    except PipelineReject as exc:
        _fail(wallpaper, str(exc))
        return "failed"
    except ffmpeg.FfmpegError as exc:
        _fail(wallpaper, str(exc))
        return "failed"
    except Exception as exc:  # transient (storage/network) — retry, then fail inspectably
        if self.request.retries >= self.max_retries:
            _fail(wallpaper, f"pipeline error after retries: {exc}")
            return "failed"
        raise self.retry(exc=exc, countdown=2**self.request.retries) from exc

    # The ONLY transition to published — one atomic write (FR-009f).
    with transaction.atomic():
        wallpaper.master_key = master_key
        wallpaper.thumbnail_key = thumb_key
        wallpaper.preview_key = preview_key
        wallpaper.thumbnail_url = storage.public_url(thumb_key)
        wallpaper.preview_video_url = storage.public_url(preview_key)
        wallpaper.resolution = f"{meta['width']}x{meta['height']}"
        wallpaper.duration_seconds = round(meta["duration"], 2)
        wallpaper.file_size_bytes = master_size
        wallpaper.failure_reason = None
        wallpaper.status = WallpaperStatus.PUBLISHED
        wallpaper.staging_key = None
        wallpaper.save()

    # Staging object is spent; the normalized master is now the source of truth.
    try:
        storage.delete_object(staging_key)
    except Exception:  # noqa: BLE001 — cleanup only; purge command sweeps leftovers
        logger.warning("could not delete staging object %s", staging_key)
    return "published"


def _fail(wallpaper, reason: str) -> None:
    """Terminal, inspectable failure — keeps staging_key so the run can be retried."""
    from apps.wallpapers.models import WallpaperStatus

    wallpaper.status = WallpaperStatus.FAILED
    wallpaper.failure_reason = reason[:2000]
    wallpaper.save(update_fields=["status", "failure_reason"])
