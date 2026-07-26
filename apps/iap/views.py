"""IAP API views — thin app-tier endpoints (Constitution V).

``verify-receipt`` and ``subscription-status`` are app tier (``X-App-Key``); they never
accept an admin JWT (Constitution II). Webhooks (signature-only) land in US2.
"""

from rest_framework.request import Request
from rest_framework.response import Response

from apps.iap import services
from apps.iap.serializers import (
    SubscriptionStatusSerializer,
    VerifyReceiptRequestSerializer,
)
from core.api import AppTierAPIView, WebhookAPIView
from core.errors import ValidationFailed


class VerifyReceiptView(AppTierAPIView):
    """POST /iap/verify-receipt — verify a store purchase and return its subscription status."""

    def post(self, request: Request) -> Response:
        serializer = VerifyReceiptRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entitlement = services.verify_receipt(**serializer.validated_data)
        return Response(SubscriptionStatusSerializer(entitlement).data)


class SubscriptionStatusView(AppTierAPIView):
    """GET /iap/subscription-status?transaction_id= — read-only entitlement lookup."""

    def get(self, request: Request) -> Response:
        transaction_id = request.query_params.get("transaction_id", "").strip()
        if not transaction_id:
            raise ValidationFailed("Query parameter 'transaction_id' is required.")
        entitlement = services.resolve_status(transaction_id)
        return Response(SubscriptionStatusSerializer(entitlement).data)


class AppleWebhookView(WebhookAPIView):
    """POST /iap/webhook/apple — App Store Server Notifications V2 (JWS-verified, signature-only)."""

    def post(self, request: Request) -> Response:
        services.process_apple_notification(request.data.get("signedPayload", ""))
        return Response({})


class GoogleWebhookView(WebhookAPIView):
    """POST /iap/webhook/google — Play RTDN via Pub/Sub push (OIDC-verified, signature-only)."""

    def post(self, request: Request) -> Response:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        services.process_google_notification(auth_header, request.data.get("message", {}))
        return Response({})
