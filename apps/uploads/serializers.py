"""Input validation for the uploads domain (Constitution XI — validate every boundary)."""

import re

from rest_framework import serializers

# Client-declared types we will presign for. Processing NEVER trusts these — real
# magic-byte sniffing decides (research D4, Constitution VII).
VIDEO_CONTENT_TYPES = {"video/mp4", "video/quicktime"}
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_CONTENT_TYPES = VIDEO_CONTENT_TYPES | IMAGE_CONTENT_TYPES

_FILENAME_RE = re.compile(r"^[\w.\- ]{1,120}$")


class PresignRequestSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=120)
    content_type = serializers.ChoiceField(choices=sorted(ALLOWED_CONTENT_TYPES))

    def validate_filename(self, value: str) -> str:
        if not _FILENAME_RE.match(value) or ".." in value or value.startswith((".", "-")):
            raise serializers.ValidationError("Filename contains unsupported characters.")
        if "." not in value:
            raise serializers.ValidationError("Filename must carry an extension.")
        return value
