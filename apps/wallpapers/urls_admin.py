"""Admin content routes (contract v0.4.0). Mounted BEFORE the Django-admin catch-all."""

from django.urls import path

from apps.wallpapers.admin_views import (
    AdminCollectionDetailView,
    AdminCollectionListCreateView,
    AdminTagDetailView,
    AdminTagListCreateView,
    AdminWallpaperDetailView,
    AdminWallpaperListCreateView,
)

urlpatterns = [
    path(
        "admin/wallpapers",
        AdminWallpaperListCreateView.as_view(),
        name="admin-wallpaper-list-create",
    ),
    path(
        "admin/wallpapers/<int:pk>",
        AdminWallpaperDetailView.as_view(),
        name="admin-wallpaper-detail",
    ),
    path("admin/tags", AdminTagListCreateView.as_view(), name="admin-tag-list-create"),
    path("admin/tags/<int:pk>", AdminTagDetailView.as_view(), name="admin-tag-detail"),
    path(
        "admin/collections",
        AdminCollectionListCreateView.as_view(),
        name="admin-collection-list-create",
    ),
    path(
        "admin/collections/<int:pk>",
        AdminCollectionDetailView.as_view(),
        name="admin-collection-detail",
    ),
]
