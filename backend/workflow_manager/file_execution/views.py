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


class FileCentricExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FileCentricExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at"]
    ordering = ["created_at"]
    filterset_class = FileExecutionFilter

    def get_queryset(self):
        execution_id = self.kwargs.get("pk")
        return FileExecution.objects.filter(workflow_execution_id=execution_id)
