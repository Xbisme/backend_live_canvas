"""Public content API views (app tier, ``X-App-Key``).

All views subclass ``core.api.AppTierAPIView`` so the app-tier trust boundary is declared once and
never mixed with the admin tier (Constitution II). Views stay thin — filtering, counting, and the
download edge live in ``services`` (Constitution V).
"""

from rest_framework.request import Request
from rest_framework.response import Response

from apps.wallpapers import services
from apps.wallpapers.pagination import WallpaperCursorPagination
from apps.wallpapers.serializers import (
    BatchRequestSerializer,
    CategorySerializer,
    CollectionDetailSerializer,
    CollectionMetaSerializer,
    TagSerializer,
    VirtualTagSerializer,
    WallpaperDetailSerializer,
    WallpaperListSerializer,
)
from core.api import AppTierAPIView


class CategoryListView(AppTierAPIView):
    """GET /categories — full curated list, unpaginated (spec FR-006)."""

    def get(self, request: Request) -> Response:
        data = CategorySerializer(services.categories_with_counts(), many=True).data
        return Response(data)


class TagListView(AppTierAPIView):
    """GET /tags — virtual "All" tag first, then real curated tags (spec FR-006a)."""

    def get(self, request: Request) -> Response:
        virtual, real_qs = services.build_tags_payload()
        payload = (
            VirtualTagSerializer(virtual, many=True).data + TagSerializer(real_qs, many=True).data
        )
        return Response(payload)


class CollectionListView(AppTierAPIView):
    """GET /collections — meta only (no items), unpaginated (spec FR-006)."""

    def get(self, request: Request) -> Response:
        data = CollectionMetaSerializer(services.collections_with_counts(), many=True).data
        return Response(data)


class CollectionDetailView(AppTierAPIView):
    """GET /collections/{id} — meta plus embedded items in curated order (spec FR-007)."""

    def get(self, request: Request, pk: int) -> Response:
        collection = services.get_collection_or_404(pk)
        items = services.collection_items(collection)
        items_data = WallpaperDetailSerializer(items, many=True).data
        data = CollectionDetailSerializer(collection, context={"items_data": items_data}).data
        return Response(data)


class WallpaperListView(AppTierAPIView):
    """GET /wallpapers — cursor pagination + filters (spec FR-008/009)."""

    def get(self, request: Request) -> Response:
        queryset = services.build_wallpaper_queryset(request.query_params)
        paginator = WallpaperCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = WallpaperListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class WallpaperDetailView(AppTierAPIView):
    """GET /wallpapers/{id} — detail with populated collections (spec FR-010)."""

    def get(self, request: Request, pk: int) -> Response:
        wallpaper = services.get_published_or_404(pk)
        return Response(WallpaperDetailSerializer(wallpaper).data)


class WallpaperBatchView(AppTierAPIView):
    """POST /wallpapers/batch — refresh Favorites; missing ids skipped silently (spec FR-011)."""

    def post(self, request: Request) -> Response:
        serializer = BatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wallpapers = services.batch_wallpapers(serializer.validated_data["ids"])
        return Response(WallpaperListSerializer(wallpapers, many=True).data)


class WallpaperDownloadUrlView(AppTierAPIView):
    """GET /wallpapers/{id}/download-url — temporary edge (spec FR-012).

    Non-premium → 200 mock URL; premium → 402 ENTITLEMENT_REQUIRED; missing/hidden → 404.
    Real entitlement + presigning arrive in BE-005.
    """

    def get(self, request: Request, pk: int) -> Response:
        wallpaper = services.get_published_or_404(pk)
        return Response(services.build_download_url(wallpaper))
