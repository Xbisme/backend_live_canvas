"""Admin-tier serializers for the content domain (contract v0.4.0).

Separate from the public serializers on purpose: the admin tier exposes lifecycle
fields (``status``, ``failure_reason``) that must never leak into app-tier payloads
(Constitution II; data-model §1).
"""

from rest_framework import serializers

from apps.wallpapers.models import Category, Orientation, Tag, Wallpaper
from apps.wallpapers.serializers import WallpaperListSerializer
from core.errors import TagNotFound


def _normalize_description(value: str | None) -> str | None:
    """Blank in → ``None`` out. The one place this invariant lives (spec FR-017).

    The client hides the "description" block on a null check alone, so an empty or
    whitespace-only string must never reach the column — it would render as an empty block.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class AdminWallpaperCreateSerializer(serializers.Serializer):
    """POST /admin/wallpapers body — validates curated references (Constitution IX)."""

    title = serializers.CharField(max_length=200)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )
    category_id = serializers.IntegerField()
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, max_length=50
    )
    orientation = serializers.ChoiceField(choices=Orientation.values)
    is_premium = serializers.BooleanField(default=False)
    source_url = serializers.URLField(max_length=500)
    license_type = serializers.CharField(max_length=120)
    upload_key = serializers.CharField(max_length=255)

    def validate_description(self, value: str | None) -> str | None:
        return _normalize_description(value)

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


class AdminWallpaperUpdateSerializer(serializers.Serializer):
    """PATCH /admin/wallpapers/{id} body — **exactly one** writable field (contract v0.7.0).

    Deliberately not a subclass of the create serializer: keeping this to a single declared
    field is what makes "the edit cannot touch anything else" structural rather than a promise.
    Extra keys in the body are simply not read (spec FR-015).
    """

    description = serializers.CharField(allow_blank=True, allow_null=True)

    def validate_description(self, value: str | None) -> str | None:
        return _normalize_description(value)


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
    # Home-screen placement (v0.7.0). Deliberately NOT validated against the section cap:
    # the cap is trimmed at read time, so flagging an 11th collection must never fail here
    # (spec FR-007). ``home_position`` is not unique either — ties break on id.
    show_on_home = serializers.BooleanField(required=False, default=False)
    home_position = serializers.IntegerField(required=False, min_value=0, default=0)
    wallpaper_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, max_length=100
    )
    cover_upload_key = serializers.CharField(max_length=255, required=False, allow_blank=True)
