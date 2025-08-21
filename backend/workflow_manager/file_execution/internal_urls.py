"""Internal API URLs for File Execution
URL patterns for file execution internal APIs.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .internal_views import (
    FileExecutionBatchCreateAPIView,
    FileExecutionBatchHashUpdateAPIView,
    FileExecutionBatchStatusUpdateAPIView,
    FileExecutionInternalViewSet,
    FileExecutionMetricsAPIView,
)

# Create router for file execution viewsets
router = DefaultRouter()
router.register(r"", FileExecutionInternalViewSet, basename="file-execution-internal")

urlpatterns = [
    # Batch operations
    path(
        "batch-create/",
        FileExecutionBatchCreateAPIView.as_view(),
        name="file-execution-batch-create",
    ),
    path(
        "batch-status-update/",
        FileExecutionBatchStatusUpdateAPIView.as_view(),
        name="file-execution-batch-status-update",
    ),
    path(
        "batch-hash-update/",
        FileExecutionBatchHashUpdateAPIView.as_view(),
        name="file-execution-batch-hash-update",
    ),
    path(
        "metrics/", FileExecutionMetricsAPIView.as_view(), name="file-execution-metrics"
    ),
    # File execution CRUD (via router)
    path("", include(router.urls)),
]
