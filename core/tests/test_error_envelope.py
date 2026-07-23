"""Structured error-envelope tests (spec US2: FR-017..FR-019).

Every error is ``{ "error": { "code", "message" } }`` with a catalog code; unhandled
exceptions become a generic 500 ``SERVER_ERROR`` with no traceback. The 500 body is
flavor-independent (the handler does not read DEBUG), so a direct handler unit test
stands in for the ``prod``/``DEBUG=False`` assertion deterministically.
"""

import pytest
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from core.errors import ErrorCode
from core.exception_handler import structured_exception_handler

_KEY = "envelope-test-key"


@pytest.fixture
def client() -> APIClient:
    c = APIClient()
    c.credentials(HTTP_X_APP_KEY=_KEY)
    return c


@override_settings(X_APP_KEY=_KEY)
def test_not_found_envelope(client: APIClient) -> None:
    response = client.get("/_probe/notfound")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND


@override_settings(X_APP_KEY=_KEY)
def test_validation_envelope(client: APIClient) -> None:
    response = client.get("/_probe/validation")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR


@override_settings(X_APP_KEY=_KEY)
def test_unhandled_exception_is_generic_500_without_traceback(client: APIClient) -> None:
    response = client.get("/_probe/boom")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    body = response.json()
    assert body["error"]["code"] == ErrorCode.SERVER_ERROR
    # No internal detail leaks to the client.
    text = response.content.decode()
    assert "Traceback" not in text
    assert "RuntimeError" not in text
    assert "Intentional probe failure" not in text


@override_settings(X_APP_KEY=_KEY)
def test_error_body_shape_is_exactly_error_code_message(client: APIClient) -> None:
    body = client.get("/_probe/validation").json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}


def test_handler_maps_unhandled_to_server_error_flavor_independent() -> None:
    # Direct unit test — the handler never reads DEBUG, so prod (DEBUG=False) yields the
    # identical safe 500 envelope with no internal detail.
    response = structured_exception_handler(
        RuntimeError("secret internal detail"), {"request": None}
    )
    assert response.status_code == 500
    assert response.data == {
        "error": {"code": ErrorCode.SERVER_ERROR, "message": "An unexpected error occurred."}
    }
    assert "secret internal detail" not in str(response.data)
