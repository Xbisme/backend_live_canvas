"""factory-boy factories for content models (Constitution X — deterministic test data)."""

import factory

from apps.wallpapers.models import (
    Category,
    Collection,
    CollectionItem,
    Tag,
    Wallpaper,
    WallpaperStatus,
)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"category-{n}")
    name = factory.Sequence(lambda n: f"Category {n}")
    icon_url = "https://cdn.example.com/icons/cat.png"


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"tag-{n}")
    name = factory.Sequence(lambda n: f"Tag {n}")


class WallpaperFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Wallpaper
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"Wallpaper {n}")
    category = factory.SubFactory(CategoryFactory)
    orientation = "portrait"
    thumbnail_url = "https://cdn.example.com/thumbs/w.jpg"
    preview_video_url = "https://cdn.example.com/preview/w.mp4"
    is_premium = False
    resolution = "1080x1920"
    duration_seconds = 8.0
    file_size_bytes = 5242880
    source_url = "https://pixabay.com/videos/example/"
    license_type = "Pixabay License"
    status = WallpaperStatus.PUBLISHED

    @factory.post_generation
    def tags(self, create, extracted, **kwargs):
        if create and extracted:
            self.tags.set(extracted)


class CollectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Collection
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"collection-{n}")
    title = factory.Sequence(lambda n: f"Collection {n}")
    author = "curator"
    description = "A curated set."
    cover_url = "https://cdn.example.com/collections/c.jpg"
    accent_color = "#FF6F9C"
    is_premium = False


class CollectionItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CollectionItem

    collection = factory.SubFactory(CollectionFactory)
    wallpaper = factory.SubFactory(WallpaperFactory)
    position = factory.Sequence(lambda n: n)
