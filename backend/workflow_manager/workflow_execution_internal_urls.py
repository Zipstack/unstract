"""Workflow Manager Internal API URLs
Defines internal API endpoints for workflow execution operations.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .internal_views import FileBatchCreateAPIView, WorkflowExecutionInternalViewSet

# Create router for internal API viewsets
router = DefaultRouter()
router.register(
    r"workflow-execution",
    WorkflowExecutionInternalViewSet,
    basename="workflow-execution-internal",
)

urlpatterns = [
    # Workflow execution internal APIs
    path(
        "workflow-execution/create-file-batch/",
        FileBatchCreateAPIView.as_view(),
        name="create-file-batch",
    ),
    # Include router URLs for viewsets (this creates the CRUD endpoints)
    path("", include(router.urls)),
]
