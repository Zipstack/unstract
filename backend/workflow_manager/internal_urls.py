"""Internal API URLs for Workflow Manager

URLs for internal APIs that workers use to communicate with Django backend.
These handle only database operations while business logic remains in workers.
"""

from django.urls import path

from . import internal_api_views, internal_views

app_name = "workflow_manager_internal"

urlpatterns = [
    # Workflow execution endpoints - specific paths first
    path(
        "execution/create/",
        internal_api_views.create_workflow_execution,
        name="create_workflow_execution",
    ),
    path(
        "execution/<str:execution_id>/",
        internal_api_views.get_workflow_execution_data,
        name="get_workflow_execution_data",
    ),
    path(
        "execution/status/",
        internal_api_views.update_workflow_execution_status,
        name="update_workflow_execution_status",
    ),
    # Tool instance endpoints
    path(
        "workflow/<str:workflow_id>/tool-instances/",
        internal_api_views.get_tool_instances_by_workflow,
        name="get_tool_instances_by_workflow",
    ),
    # Workflow compilation
    path(
        "workflow/compile/",
        internal_api_views.compile_workflow,
        name="compile_workflow",
    ),
    # File batch processing
    path(
        "file-batch/submit/",
        internal_api_views.submit_file_batch_for_processing,
        name="submit_file_batch_for_processing",
    ),
    # Workflow definition and type detection (using sophisticated class-based views)
    path(
        "workflow/<str:workflow_id>/",
        internal_views.WorkflowDefinitionAPIView.as_view(),
        name="get_workflow_definition",
    ),
    path(
        "<str:workflow_id>/endpoint/",
        internal_views.WorkflowEndpointAPIView.as_view(),
        name="get_workflow_endpoints",
    ),
    path(
        "pipeline-type/<str:pipeline_id>/",
        internal_views.PipelineTypeAPIView.as_view(),
        name="get_pipeline_type",
    ),
    path(
        "pipeline-name/<str:pipeline_id>/",
        internal_views.PipelineNameAPIView.as_view(),
        name="get_pipeline_name",
    ),
    # Batch operations (using sophisticated class-based views)
    path(
        "batch-status-update/",
        internal_views.BatchStatusUpdateAPIView.as_view(),
        name="batch_update_execution_status",
    ),
    path(
        "file-batch/",
        internal_views.FileBatchCreateAPIView.as_view(),
        name="create_file_batch",
    ),
    # File management (using sophisticated class-based views)
    path(
        "increment-files/",
        internal_views.FileCountIncrementAPIView.as_view(),
        name="increment_files",
    ),
    path(
        "file-history/create/",
        internal_views.FileHistoryCreateView.as_view(),
        name="create_file_history_entry",
    ),
    path(
        "file-history/check-batch/",
        internal_views.FileHistoryBatchCheckView.as_view(),
        name="check_file_history_batch",
    ),
    # Additional endpoints available in internal_views.py
    path(
        "source-files/<str:workflow_id>/",
        internal_views.WorkflowSourceFilesAPIView.as_view(),
        name="get_workflow_source_files",
    ),
    path(
        "execution/finalize/<str:execution_id>/",
        internal_views.ExecutionFinalizationAPIView.as_view(),
        name="finalize_execution",
    ),
    path(
        "execution/cleanup/",
        internal_views.WorkflowExecutionCleanupAPIView.as_view(),
        name="cleanup_executions",
    ),
    path(
        "execution/metrics/",
        internal_views.WorkflowExecutionMetricsAPIView.as_view(),
        name="get_execution_metrics",
    ),
    path(
        "file-execution/",
        internal_views.WorkflowFileExecutionAPIView.as_view(),
        name="workflow_file_execution",
    ),
    path(
        "file-execution/check-active",
        internal_views.WorkflowFileExecutionCheckActiveAPIView.as_view(),
        name="workflow_file_execution_check_active",
    ),
    path(
        "execute-file/",
        internal_views.WorkflowExecuteFileAPIView.as_view(),
        name="execute_workflow_file",
    ),
    path(
        "pipeline/<str:pipeline_id>/status/",
        internal_views.PipelineStatusUpdateAPIView.as_view(),
        name="update_pipeline_status",
    ),
    # File execution batch operations (using simple function views for now)
    path(
        "file-execution/batch-create/",
        internal_api_views.create_file_execution_batch,
        name="file_execution_batch_create",
    ),
    path(
        "file-execution/batch-status-update/",
        internal_api_views.update_file_execution_batch_status,
        name="file_execution_batch_status_update",
    ),
]
