import logging
from typing import Optional

from api_v2.models import APIDeployment
from django.db.models import Q, QuerySet
from pipeline_v2.models import Pipeline
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from utils.date import DateRangeKeys, DateRangeSerializer
from utils.pagination import CustomPagination
from workflow_manager.execution.enum import ExecutionEntity
from workflow_manager.execution.serializer import ExecutionSerializer
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution

logger = logging.getLogger(__name__)


class ExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> Optional[QuerySet]:
        execution_entity = self.request.query_params.get("execution_entity")

        queryset = WorkflowExecution.objects.all()

        # Filter based on execution entity
        if execution_entity == ExecutionEntity.API:
            queryset = queryset.filter(
                pipeline_id__in=APIDeployment.objects.values_list("id", flat=True)
            )
        elif execution_entity == ExecutionEntity.ETL:
            queryset = queryset.filter(
                pipeline_id__in=Pipeline.objects.filter(
                    pipeline_type=Pipeline.PipelineType.ETL
                ).values_list("id", flat=True)
            )
        elif execution_entity == ExecutionEntity.TASK:
            queryset = queryset.filter(
                pipeline_id__in=Pipeline.objects.filter(
                    pipeline_type=Pipeline.PipelineType.TASK
                ).values_list("id", flat=True)
            )
        elif execution_entity == ExecutionEntity.WORKFLOW:
            queryset = queryset.filter(
                pipeline_id=None,
                workflow_id__in=Workflow.objects.values_list("id", flat=True),
            )

        # Parse and apply date filters
        date_range_serializer = DateRangeSerializer(data=self.request.query_params)
        date_range_serializer.is_valid(raise_exception=True)

        filters = Q()
        if start_date := date_range_serializer.validated_data.get(
            DateRangeKeys.START_DATE
        ):
            filters &= Q(created_at__gte=start_date)
        if end_date := date_range_serializer.validated_data.get(DateRangeKeys.END_DATE):
            filters &= Q(created_at__lte=end_date)

        queryset = queryset.filter(filters)

        return queryset
