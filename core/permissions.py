"""Per-tier permission markers (Constitution II)."""

from rest_framework.permissions import BasePermission

from core.authentication import AppPrincipal
from core.errors import ForbiddenAdminRole, UnauthorizedAdmin


class IsAppAuthenticated(BasePermission):
    """Allow only requests authenticated as the app via ``AppKeyAuthentication``.

    Belt-and-suspenders alongside the authentication class: if the app key is absent or
    wrong, authentication already raises ``InvalidAppKey`` before this runs.
    """

    def has_permission(self, request, view) -> bool:
        return isinstance(getattr(request, "user", None), AppPrincipal)


class IsAdminStaff(BasePermission):
    """Admin tier: a real, active, **staff** Django user authenticated by JWT.

    Raises catalog exceptions directly so 401/403 keep the structured envelope:
    unauthenticated (or an app principal somehow) → ``UNAUTHORIZED_ADMIN``;
    authenticated but non-staff/disabled → ``FORBIDDEN_ADMIN_ROLE``.
    """

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or isinstance(user, AppPrincipal) or not user.is_authenticated:
            raise UnauthorizedAdmin()
        if not (user.is_active and user.is_staff):
            raise ForbiddenAdminRole()
        return True
