"""Business logic for the content domain — kept out of the thin views (Constitution V).

Covers: published-count annotation for curated lists, the synthesized "All" tag, wallpaper
filtering/search (AND tag semantics, reserved-slug stripping), and the temporary download-url
edge (real entitlement + presigning land in BE-005).
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q, QuerySet
from django.http import Http404
from django.utils import timezone

from apps.wallpapers.models import (
    RESERVED_TAG_SLUGS,
    Category,
    Collection,
    Orientation,
    Tag,
    Wallpaper,
    WallpaperStatus,
)
from core.errors import EntitlementRequired, ValidationFailed

# Reused Q for "a related wallpaper that is published and not soft-deleted".
_PUBLISHED_Q = Q(wallpapers__status=WallpaperStatus.PUBLISHED, wallpapers__deleted_at__isnull=True)

DOWNLOAD_URL_TTL = timedelta(minutes=5)  # Constitution III — presigned URLs expire ≤ 5 minutes.

# The virtual "All" tag prepended to GET /tags (contract v0.3.2). id=0 is reserved; a real
# BigAutoField PK is always ≥ 1, so there is never a collision.
VIRTUAL_ALL_TAG_ID = 0
VIRTUAL_ALL_TAG_SLUG = "all"


def categories_with_counts() -> QuerySet:
    """Categories annotated with their published-wallpaper count (spec FR-005)."""
    return Category.objects.annotate(wallpaper_count=Count("wallpapers", filter=_PUBLISHED_Q))


def tags_with_counts() -> QuerySet:
    """Real curated tags annotated with their published-wallpaper count."""
    return Tag.objects.annotate(wallpaper_count=Count("wallpapers", filter=_PUBLISHED_Q))


def build_tags_payload() -> list:
    """GET /tags data: the virtual "All" tag first, then real curated tags.

    "All" is synthesized here, never stored (Constitution IX). Its count is the total published
    wallpapers so the client can render a default chip that maps to an unfiltered list.
    """
    total_published = Wallpaper.objects.published().count()
    all_tag = {
        "id": VIRTUAL_ALL_TAG_ID,
        "slug": VIRTUAL_ALL_TAG_SLUG,
        "name": "Tất cả",
        "wallpaper_count": total_published,
    }
    return [all_tag], tags_with_counts()


def collections_with_counts() -> QuerySet:
    """Collections annotated with the count of their published member wallpapers."""
    published_member = Q(
        items__wallpaper__status=WallpaperStatus.PUBLISHED,
        items__wallpaper__deleted_at__isnull=True,
    )
    return Collection.objects.annotate(wallpaper_count=Count("items", filter=published_member))


def _parse_bool(raw: str, field: str) -> bool:
    value = raw.strip().lower()
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    raise ValidationFailed(f"Invalid boolean for '{field}': {raw!r}.")


def build_wallpaper_queryset(params) -> QuerySet:
    """Filtered, published-only wallpaper queryset for GET /wallpapers (spec FR-008/009).

    Tag semantics are AND (must match every listed slug) — implemented as chained ``.filter()``
    calls, NOT ``tags__slug__in`` (which would be OR). The reserved slug ``all`` is stripped so
    it acts as "no tag constraint" (contract v0.3.2, spec FR-006a).
    """
    qs = Wallpaper.objects.published().select_related("category").prefetch_related("tags")

    category = params.get("category")
    if category:
        qs = qs.filter(category__slug=category)

    raw_tags = params.get("tags")
    if raw_tags:
        slugs = [
            s for s in (t.strip() for t in raw_tags.split(",")) if s and s not in RESERVED_TAG_SLUGS
        ]
        for slug in slugs:
            qs = qs.filter(tags__slug=slug)  # each filter narrows further → AND

    orientation = params.get("orientation")
    if orientation:
        if orientation not in Orientation.values:
            raise ValidationFailed(f"Invalid orientation: {orientation!r}.")
        qs = qs.filter(orientation=orientation)

    is_premium = params.get("is_premium")
    if is_premium is not None and is_premium != "":
        qs = qs.filter(is_premium=_parse_bool(is_premium, "is_premium"))

    search = params.get("search")
    if search:
        qs = qs.filter(title__icontains=search)

    return qs


def get_published_or_404(wallpaper_id: int) -> Wallpaper:
    """Fetch a single published wallpaper or raise 404 (spec FR-010/013)."""
    try:
        return Wallpaper.objects.published().get(pk=wallpaper_id)
    except Wallpaper.DoesNotExist as exc:
        raise Http404("Wallpaper not found.") from exc


def get_collection_or_404(collection_id: int) -> Collection:
    try:
        return collections_with_counts().get(pk=collection_id)
    except Collection.DoesNotExist as exc:
        raise Http404("Collection not found.") from exc


def collection_items(collection: Collection) -> list:
    """Published member wallpapers in curated ``position`` order (spec FR-007, SC-006)."""
    return [
        item.wallpaper
        for item in collection.items.select_related("wallpaper__category")
        .prefetch_related("wallpaper__tags")
        .order_by("position")
        if item.wallpaper.status == WallpaperStatus.PUBLISHED and item.wallpaper.deleted_at is None
    ]


def batch_wallpapers(ids: list) -> QuerySet:
    """Published wallpapers for the given ids; missing/hidden ids are silently skipped (FR-011)."""
    return (
        Wallpaper.objects.published()
        .filter(pk__in=ids)
        .select_related("category")
        .prefetch_related("tags")
    )


def build_download_url(wallpaper: Wallpaper) -> dict:
    """Temporary download-url edge (spec FR-012).

    Non-premium → a mock URL shaped like the contract; premium → ``ENTITLEMENT_REQUIRED`` (there is
    no transaction verification until BE-005, so premium is never entitled here). Constitution III
    keeps the gate at this single edge.
    """
    if wallpaper.is_premium:
        raise EntitlementRequired()

    cdn = (settings.CDN_BASE_URL or "").rstrip("/")
    download_url = f"{cdn}/wallpapers/{wallpaper.pk}.mp4?mock=1" if cdn else wallpaper.source_url
    return {
        "download_url": download_url,
        "expires_at": timezone.now() + DOWNLOAD_URL_TTL,
    }
