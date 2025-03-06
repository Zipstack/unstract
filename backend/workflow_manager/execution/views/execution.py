import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from utils.pagination import CustomPagination
from workflow_manager.execution.filter import ExecutionFilter
from workflow_manager.execution.serializer import ExecutionSerializer
from workflow_manager.workflow_v2.models import WorkflowExecution

logger = logging.getLogger(__name__)


class ExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    filterset_class = ExecutionFilter
    queryset = WorkflowExecution.objects.all()
