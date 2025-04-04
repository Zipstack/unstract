import logging

from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from utils.pagination import CustomPagination
from workflow_manager.execution.filter import ExecutionFilter
from workflow_manager.execution.serializer import ExecutionSerializer
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution

logger = logging.getLogger(__name__)


class ExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "execution_time"]
    ordering = ["-created_at"]
    filterset_class = ExecutionFilter
    queryset = WorkflowExecution.objects.all()

    def get_queryset(self):
        base_qs = super().get_queryset()

        # Get workflows created by the user
        user_workflows = Workflow.objects.filter(created_by=self.request.user).values(
            "id"
        )

        # Query executions where either:
        # 1. The related_workflow foreign key's created_by matches the user
        # 2. The legacy workflow_id's workflow's created_by matches the user
        return base_qs.filter(
            models.Q(related_workflow__created_by=self.request.user)
            | models.Q(workflow_id__isnull=False, workflow_id__in=user_workflows)
        )
