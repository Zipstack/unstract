"""Internal API URLs for workflow execution finalization operations."""

from django.urls import path

from .internal_views import (
    cleanup_execution_resources_internal,
    execution_finalization_status_internal,
    finalize_workflow_execution_internal,
)

urlpatterns = [
    # Execution finalization endpoints
    path(
        "finalize/<str:execution_id>/",
        finalize_workflow_execution_internal,
        name="finalize-workflow-execution-internal",
    ),
    path(
        "cleanup/",
        cleanup_execution_resources_internal,
        name="cleanup-execution-resources-internal",
    ),
    path(
        "finalization-status/<str:execution_id>/",
        execution_finalization_status_internal,
        name="execution-finalization-status-internal",
    ),
]
