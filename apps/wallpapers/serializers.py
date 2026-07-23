"""DRF serializers for the content API — shapes match contract v0.3.2 exactly (Constitution I).

Two Wallpaper variants (Constitution / research R4): the list variant returns ``collections: []``
to keep large payloads light; the detail variant populates ``collections`` with mini refs.
"""

from rest_framework import serializers

from apps.wallpapers.models import Wallpaper


class _CountFromAnnotation(serializers.Serializer):
    """Mixin: expose ``wallpaper_count`` from a queryset annotation when present, else compute.

    List endpoints (/categories, /tags, /collections) annotate the count cheaply. When these
    serializers are nested inside a wallpaper payload there is no annotation, so we fall back to
    a per-object published count (acceptable at BE-003 scale; revisit if it shows up in profiling).
    """

    wallpaper_count = serializers.SerializerMethodField()

    def get_wallpaper_count(self, obj) -> int:
        annotated = getattr(obj, "wallpaper_count", None)
        if annotated is not None:
            return annotated
        return obj.wallpapers.published().count()


class CategorySerializer(_CountFromAnnotation):
    id = serializers.IntegerField()
    slug = serializers.CharField()
    name = serializers.CharField()
    icon_url = serializers.CharField(allow_blank=True)


class TagSerializer(_CountFromAnnotation):
    id = serializers.IntegerField()
    slug = serializers.CharField()
    name = serializers.CharField()


class VirtualTagSerializer(serializers.Serializer):
    """The synthesized "All" tag prepended to GET /tags — not a DB row (contract v0.3.2)."""

    id = serializers.IntegerField()
    slug = serializers.CharField()
    name = serializers.CharField()
    wallpaper_count = serializers.IntegerField()


class CollectionRefSerializer(serializers.Serializer):
    """Mini reference embedded in ``Wallpaper.collections`` (contract example)."""

    id = serializers.IntegerField()
    slug = serializers.CharField()
    title = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    is_premium = serializers.BooleanField()


class CollectionMetaSerializer(_CountFromAnnotation):
    """Collection without embedded items — GET /collections and each item of that list."""

    id = serializers.IntegerField()
    slug = serializers.CharField()
    title = serializers.CharField()
    author = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    accent_color = serializers.CharField(allow_null=True)
    is_premium = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class WallpaperSerializer(serializers.ModelSerializer):
    """Base wallpaper payload. ``collections`` is overridden per variant."""

    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    collections = serializers.SerializerMethodField()

    class Meta:
        model = Wallpaper
        fields = [
            "id",
            "title",
            "category",
            "tags",
            "orientation",
            "thumbnail_url",
            "preview_video_url",
            "is_premium",
            "resolution",
            "duration_seconds",
            "file_size_bytes",
            "download_count",
            "like_count",
            "source_url",
            "license_type",
            "collections",
            "created_at",
        ]

    def get_collections(self, obj) -> list:  # overridden by subclasses
        return []


class WallpaperListSerializer(WallpaperSerializer):
    """List/batch variant — ``collections`` intentionally empty to save payload (research R4)."""

    def get_collections(self, obj) -> list:
        return []


class WallpaperDetailSerializer(WallpaperSerializer):
    """Detail variant — ``collections`` populated with mini refs (contract GET /wallpapers/{id})."""

    def get_collections(self, obj) -> list:
        return CollectionRefSerializer(obj.collections.all(), many=True).data


class CollectionDetailSerializer(CollectionMetaSerializer):
    """GET /collections/{id} — meta plus embedded ``items`` in curated order."""

    items = serializers.SerializerMethodField()

    def get_items(self, obj) -> list:
        return self.context["items_data"]


class BatchRequestSerializer(serializers.Serializer):
    """POST /wallpapers/batch body — ``ids`` list, 1..100 integers."""

    ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        min_length=1,
        max_length=100,
    )
