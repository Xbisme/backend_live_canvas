"""URL routes for the core app — operational health endpoints.

- GET /health        → liveness (always 200 while the process serves)
- GET /health/ready  → readiness (200 when the DB is reachable, else 503)

See specs/BE-001-project-bootstrap/contracts/health-endpoints.md.
"""

from django.urls import path

from core.views import LivenessView, ReadinessView

urlpatterns = [
    path("health", LivenessView.as_view(), name="health-liveness"),
    path("health/ready", ReadinessView.as_view(), name="health-readiness"),
]
