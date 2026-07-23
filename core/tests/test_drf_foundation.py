"""DRF + feature-app foundation tests (spec US3: FR-001..FR-005).

Asserts the three feature apps are registered and model-less, the framework defaults
(cursor pagination + structured exception handler) are wired globally, the pagination
response builder emits the contract envelope, and no migrations are outstanding.
"""

from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from rest_framework.settings import api_settings

from core.exception_handler import structured_exception_handler
from core.pagination import EnvelopeCursorPagination

_FEATURE_APPS = ["wallpapers", "uploads", "iap"]


def test_feature_apps_registered_and_model_less() -> None:
    for label in _FEATURE_APPS:
        config = apps.get_app_config(label)
        assert config.name == f"apps.{label}"
        assert list(config.get_models()) == [], f"apps.{label} must have no models in BE-002"


def test_default_pagination_is_envelope_cursor() -> None:
    assert api_settings.DEFAULT_PAGINATION_CLASS is EnvelopeCursorPagination
    paginator = EnvelopeCursorPagination()
    assert paginator.page_size == 20
    assert paginator.max_page_size == 100
    assert paginator.page_size_query_param == "limit"
    assert paginator.cursor_query_param == "cursor"


def test_exception_handler_is_wired_globally() -> None:
    assert api_settings.EXCEPTION_HANDLER is structured_exception_handler


def test_pagination_response_envelope_shape() -> None:
    # Test the response builder directly with a stubbed next link — no model needed.
    paginator = EnvelopeCursorPagination()
    paginator.get_next_link = lambda: "http://testserver/x?cursor=OP4Qz&limit=20"
    body = paginator.get_paginated_response([{"id": 1}, {"id": 2}]).data
    assert body == {"items": [{"id": 1}, {"id": 2}], "next_cursor": "OP4Qz", "has_more": True}

    paginator.get_next_link = lambda: None  # end of data
    end = paginator.get_paginated_response([]).data
    assert end == {"items": [], "next_cursor": None, "has_more": False}


def test_no_offset_pagination_params() -> None:
    paginator = EnvelopeCursorPagination()
    # keyset params only — never page/page_size offset params.
    assert paginator.page_size_query_param == "limit"
    assert getattr(paginator, "cursor_query_param", None) == "cursor"


@pytest.mark.django_db
def test_no_missing_migrations() -> None:
    out = StringIO()
    # --check exits non-zero (SystemExit) if model changes lack migrations.
    try:
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
    except SystemExit as exc:  # pragma: no cover - only on drift
        assert exc.code == 0, f"Uncommitted migration drift:\n{out.getvalue()}"
