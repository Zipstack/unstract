from typing import Any

from django.db.models import QuerySet
from django_filters import rest_framework as filters
from django_filters.widgets import BooleanWidget
from utils.date import DateRangePresets, DateTimeProcessor

from workflow_manager.execution.entity import entity_condition
from workflow_manager.execution.enum import ExecutionEntity
from workflow_manager.execution.stuck import stuck_executions
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import WorkflowExecution

STUCK_PARAM = "stuck"


def stuck_requested(query_params: Any) -> bool:
    """True when ``stuck`` parses as true, by the same rule as the filter."""
    return BooleanWidget().value_from_datadict(query_params, None, STUCK_PARAM) is True


class ExecutionFilter(filters.FilterSet):
    id = filters.UUIDFilter()
    execution_entity = filters.ChoiceFilter(
        choices=[
            (ExecutionEntity.API.value, "API"),
            (ExecutionEntity.ETL.value, "ETL"),
            (ExecutionEntity.TASK.value, "TASK"),
            (ExecutionEntity.WORKFLOW.value, "WF"),
        ],
        method="filter_execution_entity",
    )
    # Lookup with query params: created_at_after, created_at_before
    created_at = filters.DateTimeFromToRangeFilter()
    status = filters.MultipleChoiceFilter(
        field_name="status", choices=ExecutionStatus.choices
    )
    date_range = filters.ChoiceFilter(
        choices=DateRangePresets.choices(),
        method="filter_by_date_range",
    )
    # Documented on ExecutionViewSet's schema.
    stuck = filters.BooleanFilter(method="filter_stuck")

    class Meta:
        model = WorkflowExecution
        fields = []

    def filter_execution_entity(
        self, queryset: QuerySet, name: str, value: str
    ) -> QuerySet:
        """Filter executions by entity type efficiently.

        The queryset is already filtered by user permissions via get_queryset(),
        so EXISTS subqueries check the entity type without fetching all IDs.
        """
        return queryset.filter(entity_condition(ExecutionEntity(value)))

    def filter_stuck(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        """Narrow to stuck executions when true; false leaves the queryset as is."""
        return stuck_executions(queryset) if value else queryset

    def filter_by_date_range(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Filters Usages based on the provided date range."""
        date_span = DateTimeProcessor.filter_date_range(value)
        if date_span:
            queryset = queryset.filter(
                created_at__gte=date_span.start_date,
                created_at__lte=date_span.end_date,
            )
        return queryset
