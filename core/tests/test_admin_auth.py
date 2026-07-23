"""US1 — admin login/refresh (spec FR-001/FR-003; contract v0.4.0 §/admin/auth/*)."""

from datetime import timedelta

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.audit.models import AuditLogEntry
from conftest import ADMIN_PASSWORD

pytestmark = pytest.mark.django_db

LOGIN = "/admin/auth/login"
REFRESH = "/admin/auth/refresh"


def _login(username: str, password: str):
    return APIClient().post(LOGIN, {"username": username, "password": password}, format="json")


def test_login_success_shape(admin_user):
    res = _login("admin", ADMIN_PASSWORD)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"access", "refresh", "expires_in"}
    assert body["expires_in"] == 30 * 60  # access lifetime — clarify Q2
    # Token carries the configured 30-minute lifetime.
    token = AccessToken(body["access"])
    assert token["exp"] - token["iat"] == 30 * 60


def test_login_wrong_password_is_401(admin_user):
    res = _login("admin", "wrong")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED_ADMIN"


def test_login_unknown_user_is_401(db):
    res = _login("ghost", "whatever")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED_ADMIN"


def test_login_non_staff_is_403(non_staff_user):
    res = _login("mortal", ADMIN_PASSWORD)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN_ADMIN_ROLE"


def test_login_disabled_account_is_403(admin_user):
    admin_user.is_active = False
    admin_user.save()
    res = _login("admin", ADMIN_PASSWORD)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN_ADMIN_ROLE"


def test_login_missing_fields_is_400(db):
    res = APIClient().post(LOGIN, {"username": "x"}, format="json")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_refresh_rotates_and_blacklists_old_token(admin_user):
    pair = _login("admin", ADMIN_PASSWORD).json()
    first = APIClient().post(REFRESH, {"refresh": pair["refresh"]}, format="json")
    assert first.status_code == 200
    body = first.json()
    assert set(body) == {"access", "refresh", "expires_in"}
    assert body["refresh"] != pair["refresh"]

    # The rotated-away refresh token must be dead (BLACKLIST_AFTER_ROTATION).
    replay = APIClient().post(REFRESH, {"refresh": pair["refresh"]}, format="json")
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "UNAUTHORIZED_ADMIN"


def test_refresh_garbage_token_is_401(db):
    res = APIClient().post(REFRESH, {"refresh": "not-a-token"}, format="json")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED_ADMIN"


def test_expired_access_token_is_401(admin_user, admin_client):
    token = AccessToken.for_user(admin_user)
    token.set_exp(lifetime=-timedelta(seconds=1))  # fail closed at/after expiry
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.get("/admin/wallpapers")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED_ADMIN"


def test_login_attempts_are_audited_without_password(admin_user):
    _login("admin", "wrong")
    _login("admin", ADMIN_PASSWORD)
    actions = list(AuditLogEntry.objects.values_list("action", flat=True))
    assert "admin.login_failed" in actions
    assert "admin.login" in actions
    for entry in AuditLogEntry.objects.all():
        blob = str(entry.metadata)
        assert ADMIN_PASSWORD not in blob and "wrong" not in blob  # no submitted secrets
        assert "password" not in {k.lower() for k in entry.metadata}  # no such key either
