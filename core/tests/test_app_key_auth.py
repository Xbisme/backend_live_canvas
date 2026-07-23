"""App-tier ``X-App-Key`` authentication tests (spec US1: FR-012..FR-016, FR-021).

Exercises the gate on a real app-tier endpoint (``GET /categories``, BE-003). Asserts the gate
rejects missing/wrong keys with the ``INVALID_APP_KEY`` envelope, is isolated from the admin
Bearer tier, fails closed on an empty configured key, leaves health endpoints ungated, and never
logs the key value.
"""

import logging

import pytest
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

_KEY = "s3cret-app-key"
_APP_ENDPOINT = "/categories"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _assert_invalid_app_key(response) -> None:
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "error": {"code": "INVALID_APP_KEY", "message": response.json()["error"]["message"]}
    }
    assert response.json()["error"]["code"] == "INVALID_APP_KEY"


@override_settings(X_APP_KEY=_KEY)
def test_missing_key_rejected(client: APIClient) -> None:
    _assert_invalid_app_key(client.get(_APP_ENDPOINT))


@override_settings(X_APP_KEY=_KEY)
def test_wrong_key_rejected(client: APIClient) -> None:
    _assert_invalid_app_key(client.get(_APP_ENDPOINT, HTTP_X_APP_KEY="nope"))


@override_settings(X_APP_KEY=_KEY)
def test_bearer_only_rejected_no_cross_tier_fallback(client: APIClient) -> None:
    # An admin-style Bearer credential must NOT authenticate the app tier.
    response = client.get(_APP_ENDPOINT, HTTP_AUTHORIZATION="Bearer some.jwt.token")
    _assert_invalid_app_key(response)


@override_settings(X_APP_KEY=_KEY)
def test_correct_key_accepted(client: APIClient) -> None:
    response = client.get(_APP_ENDPOINT, HTTP_X_APP_KEY=_KEY)
    assert response.status_code == status.HTTP_200_OK
    # A valid key reaches the real endpoint, which returns the (possibly empty) category list.
    assert isinstance(response.json(), list)


@override_settings(X_APP_KEY="")
def test_empty_configured_key_denies_everyone(client: APIClient) -> None:
    # Fail-closed misconfiguration (FR-021): with no configured key, deny all — including
    # a request that presents an empty key (no compare_digest("","") bypass).
    _assert_invalid_app_key(client.get(_APP_ENDPOINT, HTTP_X_APP_KEY=""))
    _assert_invalid_app_key(client.get(_APP_ENDPOINT, HTTP_X_APP_KEY="anything"))


@override_settings(X_APP_KEY=_KEY)
def test_health_endpoints_not_gated(client: APIClient) -> None:
    # FR-015: operational health endpoints must serve without any app key.
    assert client.get("/health").status_code == status.HTTP_200_OK


@override_settings(X_APP_KEY=_KEY)
def test_key_value_never_logged(client: APIClient, caplog) -> None:
    wrong = "leak-me-please"
    with caplog.at_level(logging.DEBUG):
        client.get(_APP_ENDPOINT, HTTP_X_APP_KEY=wrong)
    # Neither the configured key nor the presented key may appear in any log record.
    assert _KEY not in caplog.text
    assert wrong not in caplog.text
