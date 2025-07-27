"""Internal API URLs for Notification/Webhook Operations
URL patterns for webhook notification internal APIs.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .internal_views import (
    WebhookBatchAPIView,
    WebhookBatchStatusAPIView,
    WebhookInternalViewSet,
    WebhookMetricsAPIView,
    WebhookSendAPIView,
    WebhookStatusAPIView,
    WebhookTestAPIView,
)

# Create router for webhook viewsets
router = DefaultRouter()
router.register(r"", WebhookInternalViewSet, basename="webhook-internal")

urlpatterns = [
    # Webhook operation endpoints
    path("send/", WebhookSendAPIView.as_view(), name="webhook-send"),
    path("batch/", WebhookBatchAPIView.as_view(), name="webhook-batch"),
    path("test/", WebhookTestAPIView.as_view(), name="webhook-test"),
    path("status/<str:task_id>/", WebhookStatusAPIView.as_view(), name="webhook-status"),
    path(
        "batch-status/", WebhookBatchStatusAPIView.as_view(), name="webhook-batch-status"
    ),
    path("metrics/", WebhookMetricsAPIView.as_view(), name="webhook-metrics"),
    # Webhook configuration CRUD (via router)
    path("", include(router.urls)),
]
