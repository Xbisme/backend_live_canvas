"""Seed the content catalog from the committed fixture (spec FR-016).

Idempotent: re-running updates in place (``update_or_create`` by natural key) and never
duplicates rows. Deterministic and offline — no third-party API calls at run time. Collection
membership is rebuilt each run to keep the ordered ``position`` join in sync with the fixture.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.wallpapers.models import (
    Category,
    Collection,
    CollectionItem,
    Tag,
    Wallpaper,
    validate_tag_slug,
)

FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "seed_content.json"


class Command(BaseCommand):
    help = "Load the committed content fixture (categories, tags, wallpapers, collections)."

    @transaction.atomic
    def handle(self, *args, **options):
        if not FIXTURE.exists():
            raise CommandError(f"Fixture not found: {FIXTURE}")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))

        categories = {}
        for row in data.get("categories", []):
            obj, _ = Category.objects.update_or_create(
                slug=row["slug"],
                defaults={"name": row["name"], "icon_url": row.get("icon_url", "")},
            )
            categories[obj.slug] = obj

        tags = {}
        for row in data.get("tags", []):
            validate_tag_slug(
                row["slug"]
            )  # reject reserved "all" (idempotent-safe, no unique check)
            obj, _ = Tag.objects.update_or_create(slug=row["slug"], defaults={"name": row["name"]})
            tags[obj.slug] = obj

        wallpapers = {}
        for row in data.get("wallpapers", []):
            # Natural key = source_url: unique per upstream clip, stable across re-crawls
            # (titles are derived from page slugs and may collide).
            obj, _ = Wallpaper.objects.update_or_create(
                source_url=row["source_url"],
                defaults={
                    "title": row["title"],
                    "category": categories[row["category"]],
                    "orientation": row["orientation"],
                    "is_premium": row.get("is_premium", False),
                    "thumbnail_url": row.get("thumbnail_url"),
                    "preview_video_url": row.get("preview_video_url"),
                    "resolution": row.get("resolution"),
                    "duration_seconds": row.get("duration_seconds"),
                    "file_size_bytes": row.get("file_size_bytes"),
                    "license_type": row["license_type"],
                },
            )
            obj.tags.set([tags[s] for s in row.get("tags", [])])
            wallpapers[row["key"]] = obj

        for row in data.get("collections", []):
            col, _ = Collection.objects.update_or_create(
                slug=row["slug"],
                defaults={
                    "title": row["title"],
                    "author": row.get("author", ""),
                    "description": row.get("description", ""),
                    "cover_url": row.get("cover_url", ""),
                    "accent_color": row.get("accent_color"),
                    "is_premium": row.get("is_premium", False),
                },
            )
            # Rebuild ordered membership from scratch so positions match the fixture exactly.
            col.items.all().delete()
            CollectionItem.objects.bulk_create(
                [
                    CollectionItem(collection=col, wallpaper=wallpapers[key], position=idx)
                    for idx, key in enumerate(row.get("items", []))
                ]
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(categories)} categories, {len(tags)} tags, "
                f"{len(wallpapers)} wallpapers, {len(data.get('collections', []))} collections."
            )
        )
