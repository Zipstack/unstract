from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from workflow_manager.execution.views import ExecutionViewSet
from workflow_manager.workflow_v2.execution_log_view import (
    WorkflowExecutionLogViewSet as ExecutionLogViewSet,
)

execution_list = ExecutionViewSet.as_view(
    {
        "get": "list",
    }
)
execution_detail = ExecutionViewSet.as_view({"get": "retrieve"})
execution_log_list = ExecutionLogViewSet.as_view({"get": "list"})

urlpatterns = format_suffix_patterns(
    [
        path("", execution_list, name="execution-list"),
        path("<uuid:pk>/", execution_detail, name="execution-detail"),
        path("<uuid:pk>/logs/", execution_log_list, name="execution-log"),
    ]
)
