"""URL routes for the core app — operational health endpoints.

- GET /health        → liveness (always 200 while the process serves)
- GET /health/ready  → readiness (200 when the DB is reachable, else 503)

See specs/BE-001-project-bootstrap/contracts/health-endpoints.md.
"""

from django.urls import path

from core.views import (
    AppTierProbeView,
    LivenessView,
    ProbeBoomView,
    ProbeNotFoundView,
    ProbeValidationView,
    ReadinessView,
)

urlpatterns = [
    path("health", LivenessView.as_view(), name="health-liveness"),
    path("health/ready", ReadinessView.as_view(), name="health-readiness"),
    # Temporary BE-002 foundation probes (out of product contract; removed in BE-003).
    path("_probe/app-tier", AppTierProbeView.as_view(), name="probe-app-tier"),
    path("_probe/validation", ProbeValidationView.as_view(), name="probe-validation"),
    path("_probe/notfound", ProbeNotFoundView.as_view(), name="probe-notfound"),
    path("_probe/boom", ProbeBoomView.as_view(), name="probe-boom"),
]
