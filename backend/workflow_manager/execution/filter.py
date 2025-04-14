from api_v2.models import APIDeployment
from django.db.models import QuerySet
from django_filters import rest_framework as filters
from pipeline_v2.models import Pipeline
from utils.date import DateRangePresets, DateTimeProcessor

from workflow_manager.execution.enum import ExecutionEntity
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution


class ExecutionFilter(filters.FilterSet):
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

    class Meta:
        model = WorkflowExecution
        fields = []

    def filter_execution_entity(
        self, queryset: QuerySet, name: str, value: str
    ) -> QuerySet:
        if value == ExecutionEntity.API.value:
            return queryset.filter(
                pipeline_id__in=APIDeployment.objects.values_list("id", flat=True)
            )
        elif value == ExecutionEntity.ETL.value:
            return queryset.filter(
                pipeline_id__in=Pipeline.objects.filter(
                    pipeline_type=Pipeline.PipelineType.ETL
                ).values_list("id", flat=True)
            )
        elif value == ExecutionEntity.TASK.value:
            return queryset.filter(
                pipeline_id__in=Pipeline.objects.filter(
                    pipeline_type=Pipeline.PipelineType.TASK
                ).values_list("id", flat=True)
            )
        elif value == ExecutionEntity.WORKFLOW.value:
            return queryset.filter(
                pipeline_id=None,
                workflow_id__in=Workflow.objects.values_list("id", flat=True),
            )
        return queryset

    def filter_by_date_range(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Filters Usages based on the provided date range."""
        date_span = DateTimeProcessor.filter_date_range(value)
        if date_span:
            queryset = queryset.filter(
                created_at__gte=date_span.start_date,
                created_at__lte=date_span.end_date,
            )
        return queryset
