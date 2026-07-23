"""Read-only Django-admin view of the audit trail (internal staff tooling)."""

from django.contrib import admin

from apps.audit.models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_label", "action", "object_type", "object_id")
    list_filter = ("action", "object_type")
    search_fields = ("actor_label", "object_id")
    ordering = ("-created_at",)

    # Append-only: the trail is written by services.record() exclusively.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
