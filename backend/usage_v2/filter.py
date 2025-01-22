# import datetime
from typing import Any

from django.db.models import Q, QuerySet
from django_filters import rest_framework as filters
from usage_v2.models import Usage, UsageType
from usage_v2.utils import DateTimeProcessor
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models.execution import WorkflowExecution


class UsageFilter(filters.FilterSet):
    created_at_gte = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_lte = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    date_range = filters.CharFilter(method="filter_date_range")
    usage_type = filters.ChoiceFilter(choices=UsageType.choices)
    tag = filters.CharFilter(method="filter_by_tag")
    workflow_execution_id = filters.CharFilter(method="filter_by_execution_id")
    adapter_instance_id = filters.CharFilter(
        field_name="adapter_instance_id", lookup_expr="exact"
    )

    class Meta:
        model = Usage
        fields = {
            "created_at": ["exact", "lt", "lte", "gt", "gte"],
            "usage_type": ["exact"],
            "adapter_instance_id": ["exact"],
        }

    def filter_queryset(self, queryset: QuerySet) -> Any:
        """
        Apply all filters to the queryset, including smart date handling.
        """
        # First apply parent's filtering
        queryset = super().filter_queryset(queryset)

        start_date = self.form.cleaned_data.get("created_at_gte")
        end_date = self.form.cleaned_data.get("created_at_lte")
        if start_date or end_date:
            date_span = DateTimeProcessor.process_date_range(start_date, end_date)
            queryset = queryset.filter(
                created_at__range=[date_span.start_date, date_span.end_date]
            )
        return queryset

    def filter_date_range(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """
        Filters Usages based on the provided date range.
        """
        date_span = DateTimeProcessor.filter_date_range(value)
        if date_span:
            queryset = queryset.filter(created_at__gte=date_span.start_date)
        return queryset

    def filter_by_tag(self, queryset: QuerySet, name: str, value: str) -> Any:
        """
        Filters Usages based on the Tag ID or name.
        """
        queryset: QuerySet = queryset.filter(
            Q(
                run_id__in=WorkflowFileExecution.objects.filter(
                    workflow_execution__in=WorkflowExecution.objects.filter(
                        tags__name=value
                    )
                ).values_list("id", flat=True)
            )
        )
        return queryset

    def filter_by_execution_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        """
        Filters Usages based on the execution ID.
        """
        return queryset.filter(
            Q(
                run_id__in=WorkflowFileExecution.objects.filter(
                    workflow_execution__id=value
                ).values_list("id", flat=True)
            )
        )
