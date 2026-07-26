"""US1 — two-tier isolation matrix (SC-004, Constitution II).

Every ``/admin/*`` API route must reject a valid ``X-App-Key``; every app-tier route
must reject a valid admin Bearer token. Routes are DISCOVERED from the URLconfs, so
new admin endpoints (e.g. US4 tags/collections) join the matrix automatically.
"""

import pytest
from django.urls import URLPattern
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

APP_KEY = "test-app-key"


def _routes(module_name: str) -> list[str]:
    """Flatten a urlconf module into concrete paths ('<int:pk>' → '1')."""
    module = __import__(module_name, fromlist=["urlpatterns"])
    paths = []
    for pattern in module.urlpatterns:
        assert isinstance(pattern, URLPattern)
        route = str(pattern.pattern)
        paths.append("/" + route.replace("<int:pk>", "1"))
    return paths


def admin_api_routes() -> list[str]:
    routes = _routes("apps.wallpapers.urls_admin") + _routes("apps.uploads.urls")
    assert routes, "admin route discovery must never silently go empty"
    return routes


@pytest.mark.parametrize("route", admin_api_routes())
def test_app_key_never_grants_admin_access(route, settings):
    """A valid app key on ANY admin route → 401 UNAUTHORIZED_ADMIN (no fallback)."""
    settings.X_APP_KEY = APP_KEY
    client = APIClient()
    client.credentials(HTTP_X_APP_KEY=APP_KEY)
    res = client.get(route)
    assert res.status_code == 401, route
    assert res.json()["error"]["code"] == "UNAUTHORIZED_ADMIN", route


@pytest.mark.parametrize(
    "route",
    [
        "/wallpapers",
        "/categories",
        "/tags",
        "/collections",
        "/wallpapers/1/download-url",
        "/iap/subscription-status",  # app-tier IAP (BE-005)
    ],
)
def test_admin_token_never_grants_app_access(route, settings, admin_access_token):
    """A valid admin JWT on the app tier → 401 INVALID_APP_KEY (no fallback)."""
    settings.X_APP_KEY = APP_KEY
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_access_token}")
    res = client.get(route)
    assert res.status_code == 401, route
    assert res.json()["error"]["code"] == "INVALID_APP_KEY", route


def test_verify_receipt_is_app_tier_only(settings, admin_access_token):
    """POST /iap/verify-receipt rejects both no-credential and admin-JWT callers (app tier)."""
    settings.X_APP_KEY = APP_KEY
    bare = APIClient()
    assert bare.post("/iap/verify-receipt", {}, format="json").status_code == 401
    admin = APIClient()
    admin.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_access_token}")
    assert admin.post("/iap/verify-receipt", {}, format="json").status_code == 401


@pytest.mark.parametrize("route", ["/iap/webhook/apple", "/iap/webhook/google"])
def test_webhooks_are_signature_only(route, settings, admin_access_token):
    """Webhooks carry no app/admin credential — the signature decides. With no valid
    signature the request is rejected (400) regardless of X-App-Key or an admin JWT, never
    a tier 401 (Constitution II)."""
    settings.X_APP_KEY = APP_KEY
    for client in (APIClient(),):  # anonymous
        res = client.post(route, {"signedPayload": "nope", "message": {}}, format="json")
        assert res.status_code == 400, route
        assert res.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID", route
    # An admin JWT does not turn a webhook into an authenticated tier either.
    admin = APIClient()
    admin.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_access_token}")
    assert (
        admin.post(route, {"signedPayload": "nope", "message": {}}, format="json").status_code
        == 400
    )


def test_no_credentials_denied_on_both_tiers(settings):
    settings.X_APP_KEY = APP_KEY
    bare = APIClient()
    assert bare.get("/wallpapers").json()["error"]["code"] == "INVALID_APP_KEY"
    assert bare.get("/admin/wallpapers").json()["error"]["code"] == "UNAUTHORIZED_ADMIN"
