import django_filters
from django_filters import rest_framework as filters

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus


class FileExecutionFilter(filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(
        field_name="status", choices=ExecutionStatus.choices
    )
    file_name = django_filters.CharFilter(field_name="file_name", lookup_expr="icontains")

    class Meta:
        model = WorkflowFileExecution
        fields = ["status", "file_name"]
