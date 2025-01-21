from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from workflow_manager.workflow_v2.execution_log_view import WorkflowExecutionLogViewSet

execution_log_list = WorkflowExecutionLogViewSet.as_view({"get": "list"})

urlpatterns = format_suffix_patterns(
    [
        path(
            "execution/<uuid:pk>/logs/",
            execution_log_list,
            name="execution-log",
        ),
    ]
)
