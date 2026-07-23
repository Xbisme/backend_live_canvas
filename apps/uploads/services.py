"""Upload-domain services — the public surface other apps call (Constitution V).

``consume_slot`` is the single-use gate for presigned uploads (spec FR-008);
``start_processing`` enqueues the pipeline. Wallpaper admin views call these instead
of importing uploads internals.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.uploads import storage
from apps.uploads.models import UploadPurpose, UploadSlot
from core.errors import FileRejected, ValidationFailed


def consume_slot(key: str, *, expected_purpose: str) -> UploadSlot:
    """Atomically claim an upload slot (single-use; FR-008).

    Must run inside the caller's transaction: locks the row so two concurrent
    registrations of the same ``upload_key`` cannot both succeed.
    """
    try:
        slot = UploadSlot.objects.select_for_update().get(key=key)
    except UploadSlot.DoesNotExist:
        raise ValidationFailed("Unknown upload_key.") from None
    if slot.consumed_at is not None:
        raise ValidationFailed("This upload has already been registered.")
    if slot.purpose != expected_purpose:
        raise ValidationFailed("This upload was presigned for a different purpose.")
    slot.consumed_at = timezone.now()
    slot.save(update_fields=["consumed_at"])
    return slot


def check_staged_object(key: str) -> int:
    """Synchronous register-time HEAD check (remediation A1, spec FR-011).

    Cheap — no bytes are downloaded. Missing object → ``VALIDATION_ERROR``;
    oversized → ``422 FILE_REJECTED``. Content sniffing stays async (pipeline).
    """
    size = storage.head_size(key)
    if size is None:
        raise ValidationFailed("No uploaded object found for this upload_key.")
    if size > settings.UPLOAD_MAX_BYTES:
        limit_mb = settings.UPLOAD_MAX_BYTES // (1024 * 1024)
        raise FileRejected(f"File exceeds the {limit_mb} MB size ceiling.")
    return size


def start_processing(wallpaper_id: int) -> None:
    """Enqueue the media pipeline AFTER the surrounding transaction commits, so the
    worker can never race a not-yet-visible row."""
    from apps.uploads.tasks import process_wallpaper

    transaction.on_commit(lambda: process_wallpaper.delay(wallpaper_id))


def ingest_cover_image(key: str) -> str:
    """Move a sniffed-valid image from staging into the public ``covers/`` zone and
    return its CDN URL (research D4; data-model §5). Raises ``FileRejected`` when the
    staged object's real bytes are not an accepted image."""
    import magic  # deferred: needs system libmagic, only loaded on use

    head = storage.read_head(key)
    mime = magic.from_buffer(head, mime=True)
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise FileRejected("Cover upload is not a supported image.")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
    cover_key = storage.new_key(storage.COVERS_PREFIX, ext)
    client = storage.client()
    client.copy_object(
        Bucket=storage.bucket_name(storage.PUBLIC),
        Key=cover_key,
        CopySource={"Bucket": storage.bucket_name(storage.PRIVATE), "Key": key},
        ContentType=mime,
        MetadataDirective="REPLACE",
    )
    storage.delete_object(key)
    return storage.public_url(cover_key)


__all__ = [
    "UploadPurpose",
    "check_staged_object",
    "consume_slot",
    "ingest_cover_image",
    "start_processing",
]
