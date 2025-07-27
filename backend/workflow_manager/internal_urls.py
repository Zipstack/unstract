"""Internal API URLs for Workflow Manager
URL patterns for workflow execution internal APIs.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .internal_views import (
    BatchStatusUpdateAPIView,
    ExecutionFinalizationAPIView,
    FileBatchCreateAPIView,
    FileCountIncrementAPIView,
    FileHistoryBatchCheckView,
    FileHistoryCreateView,
    PipelineStatusUpdateAPIView,
    PipelineTypeAPIView,
    ToolExecutionInternalAPIView,
    WorkflowDefinitionAPIView,
    WorkflowEndpointAPIView,
    WorkflowExecuteFileAPIView,
    WorkflowExecutionCleanupAPIView,
    WorkflowExecutionInternalViewSet,
    WorkflowExecutionMetricsAPIView,
    WorkflowFileExecutionAPIView,
    WorkflowSourceFilesAPIView,
)

# Create router for workflow execution viewsets
router = DefaultRouter()
router.register(
    r"", WorkflowExecutionInternalViewSet, basename="workflow-execution-internal"
)

urlpatterns = [
    # File batch creation
    path(
        "file-batch/", FileBatchCreateAPIView.as_view(), name="workflow-file-batch-create"
    ),
    # Tool execution endpoints
    path(
        "tool-execution/workflow/<uuid:workflow_id>/instances/",
        ToolExecutionInternalAPIView.as_view(),
        name="tool-execution-instances",
    ),
    # Execution finalization
    path(
        "execution/finalize/<uuid:execution_id>/",
        ExecutionFinalizationAPIView.as_view(),
        name="execution-finalize",
    ),
    # Workflow file execution operations
    path(
        "file-execution/",
        WorkflowFileExecutionAPIView.as_view(),
        name="workflow-file-execution",
    ),
    # Execute workflow for file
    path(
        "execute-file/",
        WorkflowExecuteFileAPIView.as_view(),
        name="workflow-execute-file",
    ),
    # Workflow endpoint operations (for connection type detection)
    path(
        "<uuid:workflow_id>/endpoint/",
        WorkflowEndpointAPIView.as_view(),
        name="workflow-endpoint",
    ),
    # Workflow source files
    path(
        "<uuid:workflow_id>/source-files/",
        WorkflowSourceFilesAPIView.as_view(),
        name="workflow-source-files",
    ),
    # File count increments (for ExecutionCacheUtils functionality)
    path(
        "increment-files/",
        FileCountIncrementAPIView.as_view(),
        name="file-count-increment",
    ),
    # Pipeline status updates
    path(
        "pipeline/<uuid:pipeline_id>/status/",
        PipelineStatusUpdateAPIView.as_view(),
        name="pipeline-status-update",
    ),
    # Workflow definition
    path(
        "workflow/<uuid:workflow_id>/",
        WorkflowDefinitionAPIView.as_view(),
        name="workflow-definition",
    ),
    # Pipeline type resolution
    path(
        "pipeline-type/<uuid:pipeline_id>/",
        PipelineTypeAPIView.as_view(),
        name="pipeline-type",
    ),
    # Batch operations
    path(
        "batch-status-update/",
        BatchStatusUpdateAPIView.as_view(),
        name="batch-status-update",
    ),
    path(
        "execution-cleanup/",
        WorkflowExecutionCleanupAPIView.as_view(),
        name="execution-cleanup",
    ),
    path(
        "execution-metrics/",
        WorkflowExecutionMetricsAPIView.as_view(),
        name="execution-metrics",
    ),
    # File history operations
    path(
        "file-history/batch-check/",
        FileHistoryBatchCheckView.as_view(),
        name="file-history-batch-check",
    ),
    path(
        "file-history/create/",
        FileHistoryCreateView.as_view(),
        name="file-history-create",
    ),
    # Workflow execution CRUD (via router)
    path("", include(router.urls)),
]
