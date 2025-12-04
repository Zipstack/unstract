from api_v2.models import APIDeployment
from django.db.models import Exists, OuterRef, QuerySet
from django_filters import rest_framework as filters
from pipeline_v2.models import Pipeline
from utils.date import DateRangePresets, DateTimeProcessor

from workflow_manager.execution.enum import ExecutionEntity
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import WorkflowExecution


class ExecutionFilter(filters.FilterSet):
    id = filters.CharFilter(lookup_expr="icontains")
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
        """Filter executions by entity type efficiently.

        The queryset is already filtered by user permissions via get_queryset(),
        so we use EXISTS subqueries to check entity type without fetching all IDs.
        This is more efficient than values_list() for large datasets.
        """
        if value == ExecutionEntity.API.value:
            # Filter for API deployments using EXISTS for efficiency
            return queryset.filter(
                Exists(APIDeployment.objects.filter(id=OuterRef("pipeline_id")))
            )
        elif value == ExecutionEntity.ETL.value:
            # Filter for ETL pipelines using EXISTS
            return queryset.filter(
                Exists(
                    Pipeline.objects.filter(
                        id=OuterRef("pipeline_id"),
                        pipeline_type=Pipeline.PipelineType.ETL,
                    )
                )
            )
        elif value == ExecutionEntity.TASK.value:
            # Filter for TASK pipelines using EXISTS
            return queryset.filter(
                Exists(
                    Pipeline.objects.filter(
                        id=OuterRef("pipeline_id"),
                        pipeline_type=Pipeline.PipelineType.TASK,
                    )
                )
            )
        elif value == ExecutionEntity.WORKFLOW.value:
            # Filter for workflow-level executions (no pipeline)
            return queryset.filter(pipeline_id__isnull=True)
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
