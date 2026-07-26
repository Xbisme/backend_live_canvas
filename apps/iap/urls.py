"""IAP endpoint routes (contract v0.5.0). Mounted at the project root under ``/iap/``.

App-tier here (verify-receipt, subscription-status); signature-only webhooks land in US2.
"""

from django.urls import path

from apps.iap import views

urlpatterns = [
    path("iap/verify-receipt", views.VerifyReceiptView.as_view(), name="iap-verify-receipt"),
    path(
        "iap/subscription-status",
        views.SubscriptionStatusView.as_view(),
        name="iap-subscription-status",
    ),
    path("iap/webhook/apple", views.AppleWebhookView.as_view(), name="iap-webhook-apple"),
    path("iap/webhook/google", views.GoogleWebhookView.as_view(), name="iap-webhook-google"),
]
