"""Upload-domain models (BE-004).

``UploadSlot`` is the single-use handle for one presigned upload: issued by
``POST /admin/uploads/presign``, consumed by exactly one registration (spec FR-008 —
``select_for_update`` in the consuming service). Slots never consumed within 24 h are
orphans, surfaced by ``manage.py purge_stale_uploads`` (edge case; no background cron).
"""

from django.conf import settings
from django.db import models


class UploadPurpose(models.TextChoices):
    VIDEO = "video", "Wallpaper video"
    IMAGE = "image", "Collection cover image"


class UploadSlot(models.Model):
    """One issued presigned upload destination in the private zone (``staging/…``)."""

    key = models.CharField(max_length=255, unique=True)
    purpose = models.CharField(max_length=10, choices=UploadPurpose.choices)
    # Client-declared type — used only to presign; processing re-sniffs real bytes
    # and never trusts this value (Constitution VII).
    content_type = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="upload_slots"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        state = "consumed" if self.consumed_at else "open"
        return f"{self.key} ({state})"
