"""App-tier authentication via the ``X-App-Key`` header (Constitution II).

This authenticates the *app* — never a user (there is no account system). It is wired
OPT-IN PER TIER through ``core.api.AppTierAPIView``, never as a global DRF default, so
the admin Bearer tier (BE-004) stays strictly isolated with no cross-tier fallback.

Fail-closed: an empty/unset server ``X_APP_KEY`` never authenticates anyone (FR-021);
``prod`` additionally reads ``X_APP_KEY`` with no default so it cannot boot unconfigured.
"""

import hmac

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from core.errors import InvalidAppKey, UnauthorizedAdmin


class AppPrincipal:
    """Lightweight non-``User`` principal representing the authenticated app.

    Not persisted, not an account. Exposes just enough for DRF permission checks.
    """

    is_authenticated = True
    is_anonymous = False

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "app"


class AppKeyAuthentication(BaseAuthentication):
    """Authenticate the app by exact, constant-time ``X-App-Key`` match."""

    def authenticate(self, request):
        configured = settings.X_APP_KEY or ""
        presented = request.META.get("HTTP_X_APP_KEY", "") or ""
        # Fail closed: unconfigured key denies everyone; otherwise require an exact,
        # timing-safe match. Missing and wrong keys are indistinguishable (no leak).
        if not configured or not hmac.compare_digest(str(presented), str(configured)):
            raise InvalidAppKey()
        return (AppPrincipal(), None)

    def authenticate_header(self, request) -> str:
        # Signals the auth scheme on 401 responses; value is a scheme name, not a secret.
        return "X-App-Key"


class AdminJWTAuthentication(JWTAuthentication):
    """Admin-tier Bearer JWT (BE-004, Constitution II).

    Wraps simplejwt so every failure — missing header, malformed/expired/blacklisted
    token, unknown user — maps onto the catalog's ``UNAUTHORIZED_ADMIN`` envelope
    instead of simplejwt's own error shapes. Fail-closed: a missing header raises
    rather than returning ``None`` so no other authenticator can ever pick the
    request up (no cross-tier fallback).
    """

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            raise UnauthorizedAdmin()
        raw_token = self.get_raw_token(header)
        if raw_token is None:
            raise UnauthorizedAdmin()
        try:
            validated = self.get_validated_token(raw_token)
            user = self.get_user(validated)
        except (InvalidToken, TokenError, AuthenticationFailed) as exc:
            raise UnauthorizedAdmin() from exc
        return (user, validated)

    def authenticate_header(self, request) -> str:
        return "Bearer"
