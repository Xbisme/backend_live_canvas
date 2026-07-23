"""Admin auth endpoints — login + refresh (contract v0.4.0, Constitution II).

Lives in ``core`` (cross-cutting, no models of its own — plan §Structure Decision).
No authentication classes: credentials travel in the body. Neither endpoint accepts
``X-App-Key`` and the app tier never accepts the tokens issued here.

Every attempt is audited (spec FR-019); the submitted password is never logged or
stored anywhere.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit import services as audit
from core.errors import ForbiddenAdminRole, UnauthorizedAdmin


def _access_lifetime_seconds() -> int:
    return int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())


class AdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class AdminLoginView(APIView):
    """``POST /admin/auth/login`` — staff credentials → JWT pair (30' / 7d rotate)."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        payload = AdminLoginSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        username = payload.validated_data["username"]
        password = payload.validated_data["password"]

        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=username)
        except user_model.DoesNotExist:
            # Equalize timing with the wrong-password path (no user-enumeration oracle).
            user_model().check_password(password)
            audit.record(None, "admin.login_failed", actor_label=username, reason="unknown_user")
            raise UnauthorizedAdmin() from None

        if not user.check_password(password):
            audit.record(None, "admin.login_failed", actor_label=username, reason="bad_credentials")
            raise UnauthorizedAdmin()
        if not (user.is_active and user.is_staff):
            audit.record(None, "admin.login_failed", actor_label=username, reason="not_staff")
            raise ForbiddenAdminRole()

        refresh = RefreshToken.for_user(user)
        audit.record(user, "admin.login")
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "expires_in": _access_lifetime_seconds(),
            },
            status=status.HTTP_200_OK,
        )


class AdminRefreshView(APIView):
    """``POST /admin/auth/refresh`` — rotate: new pair, old refresh blacklisted."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError) as exc:
            # Expired / already-rotated / blacklisted / malformed — one opaque answer.
            raise UnauthorizedAdmin() from exc
        data = dict(serializer.validated_data)
        data["expires_in"] = _access_lifetime_seconds()
        return Response(data, status=status.HTTP_200_OK)
