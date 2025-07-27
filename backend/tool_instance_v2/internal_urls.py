"""Internal API URLs for tool instance operations."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    # Internal API views will be added here
    ToolExecutionInternalViewSet,
    tool_by_id_internal,
    tool_execution_status_internal,
    tool_instances_by_workflow_internal,
)

# Create router for internal API viewsets
router = DefaultRouter()
router.register(
    "executions", ToolExecutionInternalViewSet, basename="tool-execution-internal"
)

urlpatterns = [
    # Tool execution endpoints
    path("", include(router.urls)),
    path(
        "status/<str:execution_id>/",
        tool_execution_status_internal,
        name="tool-execution-status-internal",
    ),
    path(
        "workflow/<str:workflow_id>/instances/",
        tool_instances_by_workflow_internal,
        name="tool-instances-by-workflow-internal",
    ),
    path("tool/<str:tool_id>/", tool_by_id_internal, name="tool-by-id-internal"),
]
