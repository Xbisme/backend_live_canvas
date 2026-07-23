"""Polish — seed_content management command. Spec FR-016."""

import json

import pytest
from django.core.management import call_command

from apps.wallpapers.management.commands.seed_content import FIXTURE
from apps.wallpapers.models import Collection, CollectionItem, Tag, Wallpaper

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent():
    call_command("seed_content")
    wp_count = Wallpaper.objects.count()
    item_count = CollectionItem.objects.count()
    assert wp_count > 0 and item_count > 0

    call_command("seed_content")  # second run must not duplicate
    assert Wallpaper.objects.count() == wp_count
    assert CollectionItem.objects.count() == item_count


def test_seed_sets_provenance_and_no_reserved_tag():
    call_command("seed_content")
    assert all(w.source_url and w.license_type for w in Wallpaper.objects.all())
    assert not Tag.objects.filter(slug="all").exists()


def test_seed_preserves_collection_order():
    call_command("seed_content")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_by_key = {w["key"]: w["source_url"] for w in data["wallpapers"]}
    for row in data["collections"]:
        col = Collection.objects.get(slug=row["slug"])
        ordered = list(
            col.items.order_by("position").values_list("wallpaper__source_url", flat=True)
        )
        assert ordered == [source_by_key[key] for key in row["items"]]
