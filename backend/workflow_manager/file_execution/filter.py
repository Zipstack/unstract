import django_filters
from django_filters import rest_framework as filters
from workflow_manager.file_execution.models import WorkflowFileExecution


class FileExecutionFilter(filters.FilterSet):
    status = django_filters.BaseInFilter(field_name="status", lookup_expr="in")

    class Meta:
        model = WorkflowFileExecution
        fields = ["status"]
