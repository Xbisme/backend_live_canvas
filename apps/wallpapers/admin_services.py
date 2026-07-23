"""Admin-side business logic for the content domain (Constitution V, IX).

Curated integrity lives here: tag deletion guarded by usage, collection slug
conflicts, ordered membership replaced atomically. Views stay thin.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.wallpapers.models import (
    Collection,
    CollectionItem,
    Tag,
    Wallpaper,
    validate_tag_slug,
)
from core.errors import (
    CollectionSlugConflict,
    TagInUse,
    TagSlugConflict,
    ValidationFailed,
    WallpaperNotFound,
)


def soft_delete_wallpaper(pk: int) -> Wallpaper:
    try:
        wallpaper = Wallpaper.objects.get(pk=pk, deleted_at__isnull=True)
    except Wallpaper.DoesNotExist:
        raise Http404 from None
    wallpaper.deleted_at = timezone.now()
    wallpaper.save(update_fields=["deleted_at"])
    return wallpaper


def create_tag(slug: str, name: str) -> Tag:
    try:
        validate_tag_slug(slug)  # reserved "all" (Constitution IX)
    except DjangoValidationError as exc:
        raise ValidationFailed(exc.messages[0]) from exc
    if Tag.objects.filter(slug=slug).exists():
        raise TagSlugConflict()
    return Tag.objects.create(slug=slug, name=name)


def delete_tag(pk: int) -> Tag:
    try:
        tag = Tag.objects.get(pk=pk)
    except Tag.DoesNotExist:
        raise Http404 from None
    if tag.wallpapers.exists():
        raise TagInUse()
    tag.delete()
    return tag


def _validate_wallpaper_ids(wallpaper_ids: list[int]) -> None:
    wanted = set(wallpaper_ids)
    found = set(Wallpaper.objects.filter(pk__in=wanted).values_list("pk", flat=True))
    missing = sorted(wanted - found)
    if missing:
        raise WallpaperNotFound(f"Unknown wallpaper ids: {missing}.")


def _set_collection_items(collection: Collection, wallpaper_ids: list[int]) -> None:
    """Replace the ordered membership atomically (Constitution IX — same pattern as the
    seeder): a concurrent public read sees either the old or the new order, never a mix."""
    collection.items.all().delete()
    CollectionItem.objects.bulk_create(
        CollectionItem(collection=collection, wallpaper_id=wid, position=idx)
        for idx, wid in enumerate(wallpaper_ids)
    )


@transaction.atomic
def create_collection(*, slug: str, wallpaper_ids: list[int], **fields) -> Collection:
    if Collection.objects.filter(slug=slug).exists():
        raise CollectionSlugConflict()
    _validate_wallpaper_ids(wallpaper_ids)
    collection = Collection.objects.create(slug=slug, **fields)
    _set_collection_items(collection, wallpaper_ids)
    return collection


@transaction.atomic
def update_collection(pk: int, *, wallpaper_ids: list[int] | None = None, **fields) -> Collection:
    try:
        collection = Collection.objects.select_for_update().get(pk=pk)
    except Collection.DoesNotExist:
        raise Http404 from None
    new_slug = fields.get("slug")
    if new_slug and Collection.objects.exclude(pk=pk).filter(slug=new_slug).exists():
        raise CollectionSlugConflict()
    for name, value in fields.items():
        setattr(collection, name, value)
    collection.save()
    if wallpaper_ids is not None:
        _validate_wallpaper_ids(wallpaper_ids)
        _set_collection_items(collection, wallpaper_ids)
    return collection


def delete_collection(pk: int) -> Collection:
    try:
        collection = Collection.objects.get(pk=pk)
    except Collection.DoesNotExist:
        raise Http404 from None
    collection.delete()
    return collection
