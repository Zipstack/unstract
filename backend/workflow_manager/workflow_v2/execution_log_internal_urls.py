"""Internal API URLs for Execution Log Operations

URLs for internal APIs that workers use to communicate with Django backend
for execution log operations. These handle database operations while business
logic remains in workers.
"""

from django.urls import path

from . import execution_log_internal_views

app_name = "execution_log_internal"

urlpatterns = [
    # Execution log management endpoints
    path(
        "workflow-executions/by-ids/",
        execution_log_internal_views.GetWorkflowExecutionsByIdsAPIView.as_view(),
        name="get_workflow_executions_by_ids",
    ),
    path(
        "file-executions/by-ids/",
        execution_log_internal_views.GetFileExecutionsByIdsAPIView.as_view(),
        name="get_file_executions_by_ids",
    ),
    path(
        "executions/validate/",
        execution_log_internal_views.ValidateExecutionReferencesAPIView.as_view(),
        name="validate_execution_references",
    ),
    path(
        "process-log-history/",
        execution_log_internal_views.ProcessLogHistoryAPIView.as_view(),
        name="process_log_history",
    ),
]
