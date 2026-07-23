"""Product API routes for the content domain (contract v0.3.2).

Mounted at the API root in ``config/urls.py``. Health endpoints live in ``core`` and are
intentionally not part of this product contract.
"""

from django.urls import path

from apps.wallpapers.views import (
    CategoryListView,
    CollectionDetailView,
    CollectionListView,
    TagListView,
    WallpaperBatchView,
    WallpaperDetailView,
    WallpaperDownloadUrlView,
    WallpaperListView,
)

urlpatterns = [
    path("categories", CategoryListView.as_view(), name="category-list"),
    path("tags", TagListView.as_view(), name="tag-list"),
    path("collections", CollectionListView.as_view(), name="collection-list"),
    path("collections/<int:pk>", CollectionDetailView.as_view(), name="collection-detail"),
    path("wallpapers", WallpaperListView.as_view(), name="wallpaper-list"),
    path("wallpapers/batch", WallpaperBatchView.as_view(), name="wallpaper-batch"),
    path("wallpapers/<int:pk>", WallpaperDetailView.as_view(), name="wallpaper-detail"),
    path(
        "wallpapers/<int:pk>/download-url",
        WallpaperDownloadUrlView.as_view(),
        name="wallpaper-download-url",
    ),
]
