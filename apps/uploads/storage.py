"""Two-zone S3-compatible storage client (BE-004, research D3/D6).

Zones (Constitution III — the bytes are gated, the metadata is public):

- **private** (``AWS_STORAGE_BUCKET_NAME``): ``staging/`` uploads + ``masters/``
  normalized files. Reachable ONLY via short-lived presigned URLs.
- **public** (``AWS_PUBLIC_BUCKET_NAME``): ``thumbs/`` / ``previews/`` / ``covers/``.
  Public-read behind the CDN; URLs are stable ``CDN_BASE_URL + key``.

One boto3 client serves both buckets (same endpoint/credentials for MinIO dev and
R2 prod). All functions take an explicit ``bucket=`` zone so call sites read clearly.
Presigned URLs must NEVER be logged (Constitution XI).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config
from django.conf import settings

PRIVATE = "private"
PUBLIC = "public"

# Zone → prefix vocabulary (data-model §5). Keys are uuid4-based: non-guessable (FR-007).
STAGING_PREFIX = "staging/"
MASTERS_PREFIX = "masters/"
THUMBS_PREFIX = "thumbs/"
PREVIEWS_PREFIX = "previews/"
COVERS_PREFIX = "covers/"


def bucket_name(zone: str) -> str:
    if zone == PRIVATE:
        return settings.AWS_STORAGE_BUCKET_NAME
    if zone == PUBLIC:
        return settings.AWS_PUBLIC_BUCKET_NAME
    raise ValueError(f"unknown storage zone {zone!r}")


@lru_cache(maxsize=1)
def client():
    """Shared boto3 S3 client (MinIO dev / R2 prod — same S3 API)."""
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
        region_name=settings.AWS_S3_REGION_NAME or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        config=Config(signature_version="s3v4"),
    )


def new_key(prefix: str, ext: str) -> str:
    """Non-guessable object key: 128-bit uuid4 under the zone prefix."""
    return f"{prefix}{uuid.uuid4().hex}.{ext.lstrip('.')}"


def presign_upload(key: str, content_type: str) -> tuple[str, datetime]:
    """Presigned PUT into the private zone. Returns (url, expires_at)."""
    ttl = settings.PRESIGNED_UPLOAD_TTL
    url = client().generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket_name(PRIVATE), "Key": key, "ContentType": content_type},
        ExpiresIn=ttl,
    )
    return url, datetime.now(UTC) + timedelta(seconds=ttl)


def presign_download(key: str, ttl: int | None = None) -> tuple[str, datetime]:
    """Presigned single-object GET from the private zone, TTL ≤ 5 minutes
    (Constitution III). Returns (url, expires_at)."""
    ttl = min(ttl or settings.PRESIGNED_DOWNLOAD_TTL, settings.PRESIGNED_DOWNLOAD_TTL)
    url = client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name(PRIVATE), "Key": key},
        ExpiresIn=ttl,
    )
    return url, datetime.now(UTC) + timedelta(seconds=ttl)


def public_url(key: str) -> str:
    """Stable CDN URL for a public-zone object."""
    return f"{settings.CDN_BASE_URL.rstrip('/')}/{key}"


def head_size(key: str, *, zone: str = PRIVATE) -> int | None:
    """Content-Length of an object, or ``None`` if it does not exist."""
    try:
        return int(client().head_object(Bucket=bucket_name(zone), Key=key)["ContentLength"])
    except client().exceptions.ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def read_head(key: str, n: int = 2048, *, zone: str = PRIVATE) -> bytes:
    """First ``n`` bytes via range-GET — enough for magic-byte sniffing without
    downloading the file (research D4)."""
    resp = client().get_object(Bucket=bucket_name(zone), Key=key, Range=f"bytes=0-{n - 1}")
    return resp["Body"].read()


def download_file(key: str, dest: Path, *, zone: str = PRIVATE) -> None:
    client().download_file(bucket_name(zone), key, str(dest))


def upload_file(local_path: Path, key: str, *, zone: str, content_type: str = "") -> None:
    extra = {"ContentType": content_type} if content_type else {}
    client().upload_file(str(local_path), bucket_name(zone), key, ExtraArgs=extra or None)


def delete_object(key: str, *, zone: str = PRIVATE) -> None:
    client().delete_object(Bucket=bucket_name(zone), Key=key)
