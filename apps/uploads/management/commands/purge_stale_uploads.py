"""List/remove orphaned upload slots (spec edge case "orphaned uploads").

A slot presigned but never registered within 24 h is an orphan: its staging object
(if the client ever PUT it) must never become visible and just costs storage.
Deliberately a manual command — no background cron (plan/clarify decision).

Usage:
    python manage.py purge_stale_uploads            # dry-run: list only
    python manage.py purge_stale_uploads --delete   # remove slots + staging objects
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.uploads import storage
from apps.uploads.models import UploadSlot

STALE_AFTER = timedelta(hours=24)


class Command(BaseCommand):
    help = "List (default) or delete upload slots never registered within 24h."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete", action="store_true", help="Actually delete (default is dry-run)."
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - STALE_AFTER
        stale = UploadSlot.objects.filter(consumed_at__isnull=True, created_at__lt=cutoff)
        count = stale.count()
        for slot in stale.iterator():
            self.stdout.write(f"stale: {slot.key} (issued {slot.created_at:%Y-%m-%d %H:%M})")
            if options["delete"]:
                try:
                    storage.delete_object(slot.key)
                except Exception as exc:  # noqa: BLE001 — object may never have been uploaded
                    self.stderr.write(f"  could not delete object {slot.key}: {exc}")
                slot.delete()
        verb = "deleted" if options["delete"] else "found (dry-run; use --delete)"
        self.stdout.write(self.style.SUCCESS(f"{count} stale upload slot(s) {verb}."))
