"""Admin-tier serializers for the content domain (contract v0.4.0).

Separate from the public serializers on purpose: the admin tier exposes lifecycle
fields (``status``, ``failure_reason``) that must never leak into app-tier payloads
(Constitution II; data-model §1).
"""

from rest_framework import serializers

from apps.wallpapers.models import Category, Orientation, Tag, Wallpaper
from apps.wallpapers.serializers import WallpaperListSerializer
from core.errors import TagNotFound


class AdminWallpaperCreateSerializer(serializers.Serializer):
    """POST /admin/wallpapers body — validates curated references (Constitution IX)."""

    title = serializers.CharField(max_length=200)
    category_id = serializers.IntegerField()
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, max_length=50
    )
    orientation = serializers.ChoiceField(choices=Orientation.values)
    is_premium = serializers.BooleanField(default=False)
    source_url = serializers.URLField(max_length=500)
    license_type = serializers.CharField(max_length=120)
    upload_key = serializers.CharField(max_length=255)

    def validate_category_id(self, value: int) -> int:
        if not Category.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Unknown category_id.")
        return value

    def validate_tag_ids(self, value: list[int]) -> list[int]:
        wanted = set(value)
        found = set(Tag.objects.filter(pk__in=wanted).values_list("pk", flat=True))
        missing = sorted(wanted - found)
        if missing:
            # Catalog error, not a generic 400 — curated integrity (spec FR-008).
            raise TagNotFound(f"Unknown tag ids: {missing}.")
        return value


class AdminWallpaperSerializer(WallpaperListSerializer):
    """Admin list/detail item — public shape + lifecycle fields (admin tier only)."""

    status = serializers.CharField(read_only=True)
    failure_reason = serializers.CharField(read_only=True, allow_null=True)

    class Meta(WallpaperListSerializer.Meta):
        model = Wallpaper
        fields = [*WallpaperListSerializer.Meta.fields, "status", "failure_reason"]


class AdminTagCreateSerializer(serializers.Serializer):
    """POST /admin/tags body. Reserved-slug + uniqueness enforced in admin_services."""

    slug = serializers.SlugField(max_length=50)
    name = serializers.CharField(max_length=120)


class AdminCollectionSerializer(serializers.Serializer):
    """POST/PATCH /admin/collections body — ordered ``wallpaper_ids`` (Constitution IX).

    ``partial=True`` (PATCH) lets any field be omitted; on create, slug/title/
    wallpaper_ids are required. Cover arrives as ``cover_upload_key`` (an image slot
    from the presign flow) — resolved to a CDN URL by the view.
    """

    slug = serializers.SlugField(max_length=50)
    title = serializers.CharField(max_length=200)
    author = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")
    description = serializers.CharField(allow_blank=True, required=False, default="")
    accent_color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$", required=False, allow_null=True, default=None
    )
    is_premium = serializers.BooleanField(default=False)
    wallpaper_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, max_length=100
    )
    cover_upload_key = serializers.CharField(max_length=255, required=False, allow_blank=True)
