"""US1 — async pipeline state machine (spec FR-009/010/011; SC-006).

Storage, ffmpeg, and libmagic are mocked at their boundaries (Constitution X): tests
run offline and deterministic. Celery runs eagerly.
"""

import sys
import types
from unittest import mock

import pytest

from apps.uploads import tasks as pipeline
from apps.wallpapers.models import WallpaperStatus
from apps.wallpapers.tests.factories import WallpaperFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def eager_celery(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture
def fake_magic(monkeypatch):
    """Stub the ``magic`` module so tests never need system libmagic."""
    stub = types.SimpleNamespace(from_buffer=mock.Mock(return_value="video/mp4"))
    monkeypatch.setitem(sys.modules, "magic", stub)
    return stub


@pytest.fixture
def fake_storage(monkeypatch):
    st = mock.MagicMock()
    st.head_size.return_value = 10_000_000
    st.read_head.return_value = b"\x00" * 64
    st.download_file.side_effect = lambda key, dest, **kw: dest.write_bytes(b"src")
    st.upload_file.return_value = None
    st.delete_object.return_value = None
    st.public_url.side_effect = lambda key: f"http://cdn.test/{key}"
    # Real key scheme so prefixes/zones stay honest.
    from apps.uploads import storage as real

    st.new_key.side_effect = real.new_key
    for const in ("PRIVATE", "PUBLIC", "MASTERS_PREFIX", "THUMBS_PREFIX", "PREVIEWS_PREFIX"):
        setattr(st, const, getattr(real, const))
    monkeypatch.setattr(pipeline, "storage", st)
    return st


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    ff = mock.MagicMock()
    ff.FfmpegError = pipeline.ffmpeg.FfmpegError
    ff.probe.return_value = {"width": 2160, "height": 3840, "duration": 12.5}
    ff.normalize_master.side_effect = lambda src, dst: dst.write_bytes(b"m" * 2048)
    ff.extract_thumbnail.side_effect = lambda src, dst: dst.write_bytes(b"jpg")
    ff.render_preview.side_effect = lambda src, dst: dst.write_bytes(b"mp4")
    monkeypatch.setattr(pipeline, "ffmpeg", ff)
    return ff


def _processing_wallpaper():
    return WallpaperFactory(
        status=WallpaperStatus.PROCESSING,
        staging_key="staging/deadbeef.mp4",
        thumbnail_url=None,
        preview_video_url=None,
        resolution=None,
        duration_seconds=None,
        file_size_bytes=None,
    )


def test_happy_path_publishes_atomically(fake_storage, fake_ffmpeg, fake_magic):
    w = _processing_wallpaper()
    result = pipeline.process_wallpaper.delay(w.pk).get()
    w.refresh_from_db()

    assert result == "published"
    assert w.status == WallpaperStatus.PUBLISHED
    assert w.master_key.startswith("masters/")
    assert w.thumbnail_key.startswith("thumbs/")
    assert w.preview_key.startswith("previews/")
    assert w.thumbnail_url == f"http://cdn.test/{w.thumbnail_key}"
    assert w.preview_video_url == f"http://cdn.test/{w.preview_key}"
    assert w.resolution == "2160x3840"
    assert w.duration_seconds == 12.5
    assert w.file_size_bytes == 2048
    assert w.staging_key is None and w.failure_reason is None
    fake_storage.delete_object.assert_called_once_with("staging/deadbeef.mp4")


def test_disguised_file_fails_and_never_leaks_public(api, fake_storage, fake_ffmpeg, fake_magic):
    fake_magic.from_buffer.return_value = "text/plain"  # .txt renamed .mp4
    w = _processing_wallpaper()
    assert pipeline.process_wallpaper.delay(w.pk).get() == "failed"
    w.refresh_from_db()
    assert w.status == WallpaperStatus.FAILED
    assert "not an accepted video" in w.failure_reason
    assert w.staging_key == "staging/deadbeef.mp4"  # kept for inspection/retry
    # SC-006: never publicly visible.
    ids = [i["id"] for i in api.get("/wallpapers").json()["items"]]
    assert w.pk not in ids


def test_oversized_file_fails(settings, fake_storage, fake_ffmpeg, fake_magic):
    fake_storage.head_size.return_value = settings.UPLOAD_MAX_BYTES + 1
    w = _processing_wallpaper()
    assert pipeline.process_wallpaper.delay(w.pk).get() == "failed"
    w.refresh_from_db()
    assert w.status == WallpaperStatus.FAILED
    assert "ceiling" in w.failure_reason


def test_ffmpeg_error_records_reason(fake_storage, fake_ffmpeg, fake_magic):
    fake_ffmpeg.normalize_master.side_effect = pipeline.ffmpeg.FfmpegError("ffmpeg failed (rc=1)")
    w = _processing_wallpaper()
    assert pipeline.process_wallpaper.delay(w.pk).get() == "failed"
    w.refresh_from_db()
    assert w.status == WallpaperStatus.FAILED
    assert "ffmpeg failed" in w.failure_reason


def test_already_processed_is_noop(fake_storage, fake_ffmpeg, fake_magic):
    """Idempotency keys on master_key — self-hosted media exists, nothing to redo."""
    w = WallpaperFactory(status=WallpaperStatus.PUBLISHED, master_key="masters/x.mp4")
    before = w.master_key
    assert pipeline.process_wallpaper.delay(w.pk).get() == "already-processed"
    w.refresh_from_db()
    assert w.master_key == before
    fake_storage.download_file.assert_not_called()


def test_retry_after_failure_can_succeed(fake_storage, fake_ffmpeg, fake_magic):
    """failed → (fix) → re-run from the kept staging object → published (FR-010)."""
    fake_magic.from_buffer.return_value = "application/octet-stream"
    w = _processing_wallpaper()
    pipeline.process_wallpaper.delay(w.pk).get()
    w.refresh_from_db()
    assert w.status == WallpaperStatus.FAILED

    fake_magic.from_buffer.return_value = "video/mp4"
    assert pipeline.process_wallpaper.delay(w.pk).get() == "published"
    w.refresh_from_db()
    assert w.status == WallpaperStatus.PUBLISHED and w.failure_reason is None
