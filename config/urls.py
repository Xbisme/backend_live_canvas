"""Root URL configuration.

- ``admin/``  → Django's built-in admin (internal-staff tool, spec FR-019)
- ``/``       → core app routes (operational health endpoints)

Note: the product API (public / IAP / custom admin) is added in later specs and is
governed by ``contracts/openapi.yaml``. The health endpoints under core are
operational and intentionally not part of that contract.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
