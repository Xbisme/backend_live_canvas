"""Admin upload routes (contract v0.4.0). Mounted before the Django-admin catch-all."""

from django.urls import path

from apps.uploads.views import PresignView

urlpatterns = [
    path("admin/uploads/presign", PresignView.as_view(), name="admin-uploads-presign"),
]
