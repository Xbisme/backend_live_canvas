"""Append-only audit trail for admin mutations (BE-004 spec FR-019).

Rows are written synchronously inside the mutating transaction (research D8) so an
audit record and its mutation are atomic — an entry is never lost to a dead broker
and never exists without its mutation. There is deliberately NO update/delete API.
"""

from django.conf import settings
from django.db import models


class AuditLogEntry(models.Model):
    """One admin action: who did what to which object, when."""

    # SET_NULL so history survives account deletion; actor_label keeps the name.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    actor_label = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=60)  # e.g. "wallpaper.create", "admin.login_failed"
    object_type = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=60, blank=True)
    # Light detail only — services.record() rejects secret-looking content (FR-019).
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "audit log entries"

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor_label or '-'} {self.action}"
