"""App-tier permission marker (Constitution II)."""

from rest_framework.permissions import BasePermission

from core.authentication import AppPrincipal


class IsAppAuthenticated(BasePermission):
    """Allow only requests authenticated as the app via ``AppKeyAuthentication``.

    Belt-and-suspenders alongside the authentication class: if the app key is absent or
    wrong, authentication already raises ``InvalidAppKey`` before this runs.
    """

    def has_permission(self, request, view) -> bool:
        return isinstance(getattr(request, "user", None), AppPrincipal)
