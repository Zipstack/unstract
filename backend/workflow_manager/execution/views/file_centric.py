import logging

from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from utils.pagination import CustomPagination
from workflow_manager.execution.serializer import FileCentricExecutionSerializer
from workflow_manager.file_execution.models import (
    WorkflowFileExecution as FileExecution,
)

logger = logging.getLogger(__name__)


class FileCentricExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FileCentricExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at"]
    ordering = ["created_at"]

    def get_queryset(self):
        execution_id = self.kwargs.get("pk")
        return FileExecution.objects.filter(workflow_execution_id=execution_id)
