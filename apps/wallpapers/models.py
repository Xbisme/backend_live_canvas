"""Content domain models — Category, Tag, Wallpaper, Collection (Constitution V, IX).

Curated catalog: Tag and Collection are admin-curated (no free-form). Collection↔Wallpaper
is an ORDERED many-to-many via the ``CollectionItem`` join carrying ``position``. Wallpapers
carry a publish ``status`` and a soft-delete ``deleted_at``; the ``published()`` queryset is the
single gate every public read path goes through so unpublished/deleted content never leaks
(spec FR-013, SC-005).
"""

from django.core.exceptions import ValidationError
from django.db import models

# Slugs reserved for API-synthesized pseudo-resources — never a real DB row. ``all`` is the
# virtual "Tất cả" tag prepended to GET /tags (contract v0.3.2, spec FR-006a). Enforced at the
# model layer so every writer (admin, seed, future BE-004) is bound, not just one call site.
RESERVED_TAG_SLUGS = frozenset({"all"})


def validate_tag_slug(value: str) -> None:
    """Reject slugs reserved for virtual tags (Constitution IX — curated integrity)."""
    if value in RESERVED_TAG_SLUGS:
        raise ValidationError(
            f'"{value}" is a reserved slug and cannot be used for a real tag.',
            code="reserved_slug",
        )


class Orientation(models.TextChoices):
    PORTRAIT = "portrait", "Portrait"
    LANDSCAPE = "landscape", "Landscape"
    SQUARE = "square", "Square"


class WallpaperStatus(models.TextChoices):
    PROCESSING = "processing", "Processing"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"


class Category(models.Model):
    """Top-level curated grouping. A wallpaper belongs to exactly one category."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    icon_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    """Curated label, many-to-many with Wallpaper. Slug ``all`` is reserved (virtual tag)."""

    slug = models.SlugField(unique=True, validators=[validate_tag_slug])
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WallpaperQuerySet(models.QuerySet):
    def published(self) -> "WallpaperQuerySet":
        """The only content visible to the public tier: published and not soft-deleted."""
        return self.filter(status=WallpaperStatus.PUBLISHED, deleted_at__isnull=True)


class Wallpaper(models.Model):
    """Central content unit (a live-wallpaper video)."""

    title = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="wallpapers")
    tags = models.ManyToManyField(Tag, blank=True, related_name="wallpapers")
    orientation = models.CharField(max_length=10, choices=Orientation.choices)

    # Media-derived fields — the contract models these as JSON ``null`` while processing
    # (BE-004 pipeline), so a real NULL is intentional here (not the usual blank="" convention).
    # max_length=500: real-world CDN/source URLs (e.g. Pexels page slugs) exceed the 200 default.
    thumbnail_url = models.URLField(max_length=500, null=True, blank=True)  # noqa: DJ001 — contract-nullable
    preview_video_url = models.URLField(max_length=500, null=True, blank=True)  # noqa: DJ001 — contract-nullable
    resolution = models.CharField(max_length=20, null=True, blank=True)  # noqa: DJ001 — contract-nullable
    duration_seconds = models.FloatField(null=True, blank=True)
    file_size_bytes = models.BigIntegerField(null=True, blank=True)

    is_premium = models.BooleanField(default=False)
    download_count = models.PositiveIntegerField(default=0)
    like_count = models.PositiveIntegerField(default=0)

    # Provenance / license — required for source-terms compliance (spec FR-004).
    source_url = models.URLField(max_length=500)
    license_type = models.CharField(max_length=120)

    # Storage keys (BE-004 pipeline, data-model §1). masters/* live in the PRIVATE zone
    # (non-guessable uuid keys, presigned-only — Constitution III); thumbs/previews in
    # the PUBLIC zone (their URLs mirror into thumbnail_url/preview_video_url).
    # master_key IS NULL ⇔ no self-hosted file yet (backfill's resume condition).
    master_key = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001 — null = not yet processed
    staging_key = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001 — kept while processing/failed for retry
    thumbnail_key = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    preview_key = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    # Why a run failed (truncated ffmpeg stderr / sniff verdict). Admin tier only —
    # never serialized on the public tier.
    failure_reason = models.TextField(null=True, blank=True)  # noqa: DJ001

    status = models.CharField(
        max_length=12, choices=WallpaperStatus.choices, default=WallpaperStatus.PUBLISHED
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    collections = models.ManyToManyField(
        "Collection", through="CollectionItem", related_name="wallpapers", blank=True
    )

    objects = WallpaperQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # Matches the cursor keyset ordering ("-created_at", "-id") for index-friendly paging.
            models.Index(fields=["-created_at", "-id"], name="wp_created_id_idx"),
            models.Index(fields=["is_premium"], name="wp_is_premium_idx"),
            models.Index(fields=["deleted_at"], name="wp_deleted_at_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class Collection(models.Model):
    """Curated collection — ordered many-to-many with Wallpaper via ``CollectionItem``."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    cover_url = models.URLField(max_length=500, blank=True)
    accent_color = models.CharField(max_length=9, null=True, blank=True)  # noqa: DJ001 — contract-nullable
    is_premium = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title


class CollectionItem(models.Model):
    """Ordered join row: a wallpaper's ``position`` within a collection (Constitution IX)."""

    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="items")
    wallpaper = models.ForeignKey(Wallpaper, on_delete=models.CASCADE, related_name="memberships")
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["collection", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "wallpaper"], name="uniq_collection_wallpaper"
            ),
            models.UniqueConstraint(
                fields=["collection", "position"], name="uniq_collection_position"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.collection.slug}[{self.position}] → {self.wallpaper_id}"
