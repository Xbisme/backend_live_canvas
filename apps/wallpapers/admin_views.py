"""Admin content endpoints (contract v0.4.0) — ``AdminTierAPIView`` only.

Thin views (Constitution V): validation in serializers, orchestration in services,
uploads-domain access through ``apps.uploads.services`` public functions only.
"""

from django.db import transaction
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit import services as audit
from apps.uploads import services as upload_services
from apps.wallpapers import admin_services, services
from apps.wallpapers.admin_serializers import (
    AdminCollectionSerializer,
    AdminTagCreateSerializer,
    AdminWallpaperCreateSerializer,
    AdminWallpaperSerializer,
)
from apps.wallpapers.models import Wallpaper, WallpaperStatus
from apps.wallpapers.pagination import WallpaperCursorPagination
from apps.wallpapers.serializers import CollectionMetaSerializer, TagSerializer
from core.api import AdminTierAPIView
from core.errors import ValidationFailed


class AdminWallpaperListCreateView(AdminTierAPIView):
    """POST /admin/wallpapers (register upload) · GET /admin/wallpapers (all states)."""

    def post(self, request: Request) -> Response:
        payload = AdminWallpaperCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        # Synchronous, cheap gate (remediation A1): object exists + ≤ size ceiling.
        upload_services.check_staged_object(data["upload_key"])

        with transaction.atomic():
            slot = upload_services.consume_slot(
                data["upload_key"], expected_purpose=upload_services.UploadPurpose.VIDEO
            )
            wallpaper = Wallpaper.objects.create(
                title=data["title"],
                category_id=data["category_id"],
                orientation=data["orientation"],
                is_premium=data["is_premium"],
                source_url=data["source_url"],
                license_type=data["license_type"],
                status=WallpaperStatus.PROCESSING,
                staging_key=slot.key,
            )
            wallpaper.tags.set(data["tag_ids"])
            audit.record(request.user, "upload.register", wallpaper, upload_key=slot.key)
            audit.record(request.user, "wallpaper.create", wallpaper, title=wallpaper.title)
            # Enqueued on commit — the worker never sees an uncommitted row.
            upload_services.start_processing(wallpaper.pk)

        return Response(
            AdminWallpaperSerializer(wallpaper).data, status=http_status.HTTP_201_CREATED
        )

    def get(self, request: Request) -> Response:
        queryset = Wallpaper.objects.filter(deleted_at__isnull=True)
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in WallpaperStatus.values:
                raise ValidationFailed(f"Unknown status {status_filter!r}.")
            queryset = queryset.filter(status=status_filter)
        paginator = WallpaperCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AdminWallpaperSerializer(page, many=True).data)


class AdminWallpaperDetailView(AdminTierAPIView):
    """DELETE /admin/wallpapers/{id} — soft delete (Constitution IX)."""

    def delete(self, request: Request, pk: int) -> Response:
        wallpaper = admin_services.soft_delete_wallpaper(pk)
        audit.record(request.user, "wallpaper.delete", wallpaper, title=wallpaper.title)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class AdminTagListCreateView(AdminTierAPIView):
    """POST /admin/tags · GET /admin/tags (with usage counts) — curated vocabulary."""

    def post(self, request: Request) -> Response:
        payload = AdminTagCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with transaction.atomic():
            tag = admin_services.create_tag(**payload.validated_data)
            audit.record(request.user, "tag.create", tag, slug=tag.slug)
        return Response(TagSerializer(tag).data, status=http_status.HTTP_201_CREATED)

    def get(self, request: Request) -> Response:
        return Response(TagSerializer(services.tags_with_counts(), many=True).data)


class AdminTagDetailView(AdminTierAPIView):
    """DELETE /admin/tags/{id} — refuses while in use (TAG_IN_USE, Constitution IX)."""

    def delete(self, request: Request, pk: int) -> Response:
        with transaction.atomic():
            tag = admin_services.delete_tag(pk)
            audit.record(request.user, "tag.delete", slug=tag.slug)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


def _resolve_cover(data: dict) -> dict:
    """Swap ``cover_upload_key`` (image slot) for a public ``cover_url`` (research D4)."""
    cover_key = data.pop("cover_upload_key", "")
    if cover_key:
        with transaction.atomic():
            upload_services.consume_slot(
                cover_key, expected_purpose=upload_services.UploadPurpose.IMAGE
            )
        data["cover_url"] = upload_services.ingest_cover_image(cover_key)
    return data


class AdminCollectionListCreateView(AdminTierAPIView):
    """POST /admin/collections · GET /admin/collections."""

    def post(self, request: Request) -> Response:
        payload = AdminCollectionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = _resolve_cover(dict(payload.validated_data))
        wallpaper_ids = data.pop("wallpaper_ids")
        with transaction.atomic():  # mutation + audit are one transaction (research D8)
            collection = admin_services.create_collection(wallpaper_ids=wallpaper_ids, **data)
            audit.record(
                request.user,
                "collection.create",
                collection,
                slug=collection.slug,
                item_count=len(wallpaper_ids),
            )
        return Response(
            CollectionMetaSerializer(collection).data, status=http_status.HTTP_201_CREATED
        )

    def get(self, request: Request) -> Response:
        return Response(
            CollectionMetaSerializer(services.collections_with_counts(), many=True).data
        )


class AdminCollectionDetailView(AdminTierAPIView):
    """PATCH /admin/collections/{id} (atomic reorder) · DELETE /admin/collections/{id}."""

    def patch(self, request: Request, pk: int) -> Response:
        payload = AdminCollectionSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = _resolve_cover(dict(payload.validated_data))
        wallpaper_ids = data.pop("wallpaper_ids", None)
        with transaction.atomic():  # mutation + audit are one transaction (research D8)
            collection = admin_services.update_collection(pk, wallpaper_ids=wallpaper_ids, **data)
            audit.record(request.user, "collection.update", collection, slug=collection.slug)
        return Response(CollectionMetaSerializer(collection).data)

    def delete(self, request: Request, pk: int) -> Response:
        with transaction.atomic():
            collection = admin_services.delete_collection(pk)
            audit.record(request.user, "collection.delete", slug=collection.slug)
        return Response(status=http_status.HTTP_204_NO_CONTENT)
