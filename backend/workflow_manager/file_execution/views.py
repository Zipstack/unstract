from django.db.models import OuterRef, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from utils.pagination import CustomPagination

from workflow_manager.file_execution.filter import FileExecutionFilter
from workflow_manager.file_execution.models import (
    WorkflowFileExecution as FileExecution,
)
from workflow_manager.file_execution.serializers import FileCentricExecutionSerializer
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog


class FileCentricExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FileCentricExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "execution_time", "file_size"]
    ordering = ["created_at"]
    filterset_class = FileExecutionFilter

    def get_queryset(self):
        execution_id = self.kwargs.get("pk")

        # Subquery to get latest non-DEBUG/WARN log data per file execution
        # Avoids N+1 queries when serializing status_msg
        latest_log_subquery = (
            ExecutionLog.objects.filter(file_execution=OuterRef("pk"))
            .exclude(data__level__in=["DEBUG", "WARN"])
            .order_by("-event_time")
            .values("data")[:1]
        )

        return FileExecution.objects.filter(workflow_execution_id=execution_id).annotate(
            latest_log_data=Subquery(latest_log_subquery)
        )
