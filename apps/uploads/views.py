"""Admin upload endpoints — presign (contract v0.4.0 §POST /admin/uploads/presign)."""

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit import services as audit
from apps.uploads import storage
from apps.uploads.models import UploadPurpose, UploadSlot
from apps.uploads.serializers import VIDEO_CONTENT_TYPES, PresignRequestSerializer
from core.api import AdminTierAPIView


class PresignView(AdminTierAPIView):
    """Issue a single-use presigned PUT into the private staging zone.

    The API never touches file bytes (Constitution VII) — the client PUTs straight
    to storage, then registers the returned ``upload_key``.
    """

    def post(self, request: Request) -> Response:
        payload = PresignRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        filename = payload.validated_data["filename"]
        content_type = payload.validated_data["content_type"]

        ext = filename.rsplit(".", 1)[-1].lower()
        key = storage.new_key(storage.STAGING_PREFIX, ext)
        purpose = (
            UploadPurpose.VIDEO if content_type in VIDEO_CONTENT_TYPES else UploadPurpose.IMAGE
        )
        UploadSlot.objects.create(
            key=key, purpose=purpose, content_type=content_type, created_by=request.user
        )
        upload_url, expires_at = storage.presign_upload(key, content_type)
        # Audit the slot issuance — key only, NEVER the presigned URL (FR-019).
        audit.record(request.user, "upload.presign", upload_key=key, content_type=content_type)
        return Response(
            {"upload_url": upload_url, "upload_key": key, "expires_at": expires_at},
            status=status.HTTP_200_OK,
        )
