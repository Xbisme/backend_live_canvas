"""DRF serializers for the IAP API — shapes match contract v0.5.0 exactly (Constitution I).

Thin boundary validation only (Constitution XI): parse/validate in, serialize out. The
verification and entitlement logic lives in ``apps.iap.services``.
"""

from rest_framework import serializers

from apps.iap.models import EntitlementStatus, IapPlatform


class VerifyReceiptRequestSerializer(serializers.Serializer):
    """Body of ``POST /iap/verify-receipt`` (contract ``VerifyReceiptRequest``)."""

    platform = serializers.ChoiceField(choices=IapPlatform.values)
    receipt_data = serializers.CharField()
    transaction_id = serializers.CharField()
    product_id = serializers.CharField(required=False, allow_blank=True, default="")
    device_id = serializers.CharField(required=False, allow_blank=True, default="")


class SubscriptionStatusSerializer(serializers.Serializer):
    """Response of verify-receipt + subscription-status (contract ``SubscriptionStatus``).

    Reads straight off a ``SubscriptionEntitlement`` instance; ``status`` is already the
    contract enum value.
    """

    transaction_id = serializers.SerializerMethodField()
    product_id = serializers.CharField()
    status = serializers.ChoiceField(choices=EntitlementStatus.values)
    expires_at = serializers.DateTimeField(allow_null=True)
    auto_renew = serializers.BooleanField()

    def get_transaction_id(self, obj) -> str:
        """The stable original transaction id — the id every chain member resolves to."""
        return obj.original_transaction_id
