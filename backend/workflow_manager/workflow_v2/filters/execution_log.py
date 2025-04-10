from django.db.models.query import QuerySet
from django_filters import CharFilter, FilterSet, ModelChoiceFilter
from rest_framework.request import Request

from unstract.sdk.constants import LogLevel
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog


def get_file_executions(request: Request | None) -> QuerySet:
    """Callable for ModelChoiceFilter to dynamically filter file_execution_id."""
    if request is None or not hasattr(request, "parser_context"):
        return WorkflowFileExecution.objects.none()

    # Extract execution_id from URL kwargs
    execution_id = request.parser_context["kwargs"].get("pk")
    if not execution_id:
        return WorkflowFileExecution.objects.none()

    return WorkflowFileExecution.objects.filter(workflow_execution_id=execution_id)


class ExecutionLogFilter(FilterSet):
    file_execution_id = ModelChoiceFilter(
        queryset=get_file_executions,
        null_label="null",
    )

    log_level = CharFilter(field_name="data__level", method="filter_logs")

    class Meta:
        model = ExecutionLog
        fields = ["file_execution_id", "log_level"]

    def filter_logs(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        levels = {
            LogLevel.DEBUG.value: 0,
            LogLevel.INFO.value: 1,
            LogLevel.WARN.value: 2,
            LogLevel.ERROR.value: 3,
        }
        min_level = levels.get(value, 1)  # Default to INFO if not found
        return queryset.filter(
            data__level__in=[
                level for level, severity in levels.items() if severity >= min_level
            ]
        )
