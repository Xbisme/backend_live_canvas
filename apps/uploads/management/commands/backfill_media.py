"""Bulk backfill: push the seeded catalog through the real media pipeline (US2).

Reads the committed fixture's ``local_path`` ↔ ``source_url`` mapping, uploads each
original file from the local dataset into the private staging zone, and enqueues the
SAME ``process_wallpaper`` task as a normal admin upload — one processing path
(spec FR-015). Idempotent and resumable (FR-016): a wallpaper with ``master_key``
set is done and skipped; missing files are reported and skipped; re-running
completes only the remainder.

Usage:
    python manage.py backfill_media [--dataset-dir DIR] [--limit N] [--dry-run]
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.audit import services as audit
from apps.uploads import storage
from apps.uploads.tasks import process_wallpaper
from apps.wallpapers.models import Wallpaper, WallpaperStatus

FIXTURE = Path(__file__).resolve().parents[3] / "wallpapers" / "fixtures" / "seed_content.json"


class Command(BaseCommand):
    help = "Upload seeded wallpapers' local files to storage and process them (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset-dir",
            default=settings.BACKFILL_DATASET_DIR,
            help="Local dataset root (default: BACKFILL_DATASET_DIR env).",
        )
        parser.add_argument("--limit", type=int, default=None, help="Process at most N items.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Report what would happen; change nothing."
        )
        parser.add_argument(
            "--requeue-stale",
            action="store_true",
            help=(
                "Also re-enqueue staged items that are not failed (use when the broker "
                "lost its queue, e.g. Redis was wiped). Default: staged non-failed items "
                "are assumed in-flight and skipped."
            ),
        )

    def handle(self, *args, **options):
        dataset_dir = Path(options["dataset_dir"] or "").expanduser()
        if not dataset_dir.is_dir():
            raise CommandError(
                f"Dataset directory not found: {dataset_dir or '(unset)'} — "
                "set BACKFILL_DATASET_DIR or pass --dataset-dir."
            )
        if not FIXTURE.exists():
            raise CommandError(f"Fixture not found: {FIXTURE}")

        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        local_path_by_source = {
            row["source_url"]: row.get("local_path")
            for row in fixture.get("wallpapers", [])
            if row.get("local_path")
        }

        # Resume condition (research D7): master_key IS NULL ⇔ not yet self-hosted.
        # Soft-deleted rows are never touched (spec edge case).
        pending = Wallpaper.objects.filter(
            master_key__isnull=True, deleted_at__isnull=True
        ).order_by("id")
        done_count = Wallpaper.objects.filter(master_key__isnull=False).count()

        processed = requeued = inflight = skipped_missing = 0
        limit = options["limit"]
        for wallpaper in pending.iterator():
            if limit is not None and processed >= limit:
                break

            # Already staged (interrupted run / failed item): the object is in storage —
            # never re-upload (FR-016 resume). failed → re-enqueue for retry; otherwise
            # assume the original task is still in the broker unless --requeue-stale.
            if wallpaper.staging_key:
                if wallpaper.status == WallpaperStatus.FAILED or options["requeue_stale"]:
                    if not options["dry_run"]:
                        process_wallpaper.delay(wallpaper.pk)
                    requeued += 1
                else:
                    inflight += 1
                continue

            local_rel = local_path_by_source.get(wallpaper.source_url)
            local_file = dataset_dir / local_rel if local_rel else None
            if not local_rel or not local_file.is_file():
                skipped_missing += 1
                self.stderr.write(f"missing file for wallpaper {wallpaper.pk}: {local_rel!r}")
                continue

            if options["dry_run"]:
                processed += 1
                self.stdout.write(f"[dry-run] would upload {local_rel} → wallpaper {wallpaper.pk}")
                continue

            ext = local_file.suffix.lstrip(".") or "mp4"
            staging_key = storage.new_key(storage.STAGING_PREFIX, ext)
            storage.upload_file(
                local_file, staging_key, zone=storage.PRIVATE, content_type="video/mp4"
            )
            # Provenance (source_url/license/author) is deliberately untouched (FR-016).
            wallpaper.staging_key = staging_key
            wallpaper.save(update_fields=["staging_key"])
            process_wallpaper.delay(wallpaper.pk)
            processed += 1
            self.stdout.write(f"queued wallpaper {wallpaper.pk} ({local_rel})")

        if not options["dry_run"]:
            audit.record(
                None,
                "backfill.run",
                actor_label="backfill_media",
                processed=processed,
                requeued=requeued,
                skipped_done=done_count,
                skipped_missing=skipped_missing,
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill summary: processed={processed} requeued={requeued} "
                f"in-flight={inflight} skipped-done={done_count} "
                f"skipped-missing={skipped_missing}" + (" (dry-run)" if options["dry_run"] else "")
            )
        )
