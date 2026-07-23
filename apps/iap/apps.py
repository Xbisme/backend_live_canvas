from django.apps import AppConfig


class IapConfig(AppConfig):
    """IAP domain — verify-receipt, Apple/Google webhooks, entitlement.

    Model-less shell in BE-002; verification + entitlement land in BE-005.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.iap"
