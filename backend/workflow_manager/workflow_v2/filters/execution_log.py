from uuid import UUID

from django.db.models.query import QuerySet
from django_filters import CharFilter, FilterSet

from unstract.sdk1.constants import LogLevel
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog


class ExecutionLogFilter(FilterSet):
    file_execution_id = CharFilter(
        field_name="file_execution_id", method="filter_file_execution"
    )

    log_level = CharFilter(field_name="data__level", method="filter_logs")

    def filter_file_execution(
        self, queryset: QuerySet, name: str, value: str
    ) -> QuerySet:
        if value == "null":
            return queryset.filter(file_execution_id__isnull=True)
        try:
            UUID(value)
        except ValueError:
            return queryset.none()
        return queryset.filter(file_execution_id=value)

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
