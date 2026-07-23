"""URL routes for the core app.

Operational health endpoints (NOT part of the product contract):

- GET /health        → liveness (always 200 while the process serves)
- GET /health/ready  → readiness (200 when the DB is reachable, else 503)

Admin auth endpoints (contract v0.4.0, BE-004):

- POST /admin/auth/login    → staff credentials → JWT pair
- POST /admin/auth/refresh  → rotate the refresh token
"""

from django.urls import path

from core.auth_views import AdminLoginView, AdminRefreshView
from core.views import LivenessView, ReadinessView

urlpatterns = [
    path("health", LivenessView.as_view(), name="health-liveness"),
    path("health/ready", ReadinessView.as_view(), name="health-readiness"),
    path("admin/auth/login", AdminLoginView.as_view(), name="admin-auth-login"),
    path("admin/auth/refresh", AdminRefreshView.as_view(), name="admin-auth-refresh"),
]
