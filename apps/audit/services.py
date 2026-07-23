"""The single write path into the audit log (Constitution V — cross-app service).

Every admin mutation calls ``record()`` inside its own DB transaction. The sanitize
guard is the one chokepoint that keeps secrets out of the trail (spec FR-019): it
rejects metadata that smells like credentials, tokens, or signed URLs instead of
silently storing them.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from apps.audit.models import AuditLogEntry

# Metadata KEYS that must never be audited, whatever their value.
_FORBIDDEN_KEYS = frozenset(
    {"password", "token", "access", "refresh", "authorization", "secret", "receipt"}
)
# Value substrings that indicate a signed URL or bearer credential leaked into metadata.
_FORBIDDEN_VALUE_MARKERS = ("x-amz-signature", "x-amz-credential", "bearer ey", "jwt ey")


class AuditSanitizationError(ValueError):
    """Raised when metadata would leak a secret into the audit trail."""


def _check_clean(value: Any) -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                raise AuditSanitizationError(f"audit metadata must not contain key {key!r}")
            _check_clean(sub)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _check_clean(item)
    elif isinstance(value, str):
        lowered = value.lower()
        for marker in _FORBIDDEN_VALUE_MARKERS:
            if marker in lowered:
                raise AuditSanitizationError("audit metadata must not contain signed/bearer values")


def record(
    actor,
    action: str,
    obj: models.Model | None = None,
    *,
    actor_label: str = "",
    **metadata: Any,
) -> AuditLogEntry:
    """Append one audit entry. Call inside the mutating transaction.

    ``actor`` may be None (e.g. failed login before a user is resolved) — pass
    ``actor_label`` with the submitted username then. NEVER pass passwords, tokens,
    or presigned URLs in ``metadata``; the guard raises if you do.
    """
    _check_clean(metadata)
    return AuditLogEntry.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_label=actor_label or (getattr(actor, "get_username", lambda: "")() or ""),
        action=action,
        object_type=obj._meta.model_name if obj is not None else "",
        object_id=str(obj.pk) if obj is not None and obj.pk is not None else "",
        metadata=metadata,
    )
