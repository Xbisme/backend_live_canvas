"""Shared API base classes.

``AppTierAPIView`` is the base every public + IAP endpoint (BE-003 / BE-005) subclasses.
It binds the app-tier ``X-App-Key`` authentication + permission so the app-tier trust
boundary is declared in exactly one place and never leaks onto the admin tier
(Constitution II, V).
"""

from rest_framework.views import APIView

from core.authentication import AdminJWTAuthentication, AppKeyAuthentication
from core.permissions import IsAdminStaff, IsAppAuthenticated


class AppTierAPIView(APIView):
    """Base view for the public + IAP (app) tier — requires a valid ``X-App-Key``."""

    authentication_classes = [AppKeyAuthentication]
    permission_classes = [IsAppAuthenticated]


class AdminTierAPIView(APIView):
    """Base view for the ``/admin/*`` tier — requires a Bearer admin JWT of a staff user.

    Strictly symmetric with ``AppTierAPIView`` and never mixed with it: an ``X-App-Key``
    is meaningless here and an admin JWT is meaningless on the app tier (Constitution II —
    no fallback in either direction).
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminStaff]
