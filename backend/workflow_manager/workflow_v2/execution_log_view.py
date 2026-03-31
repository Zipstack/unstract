import logging

from django.db.models import Q
from django.db.models.query import QuerySet
from permissions.permission import IsOwner
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.versioning import URLPathVersioning
from utils.pagination import CustomPagination

from workflow_manager.workflow_v2.filters import ExecutionLogFilter
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog
from workflow_manager.workflow_v2.serializers import WorkflowExecutionLogSerializer

logger = logging.getLogger(__name__)


class WorkflowExecutionLogViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = WorkflowExecutionLogSerializer
    pagination_class = CustomPagination
    ordering_fields = ["event_time"]
    ordering = ["event_time"]
    filterset_class = ExecutionLogFilter

    def get_queryset(self) -> QuerySet:
        execution_id = self.kwargs.get("pk")

        # Query by execution_id for backward compatibility
        # Remove filter after execution_id is removed
        return ExecutionLog.objects.filter(
            Q(wf_execution_id=execution_id) | Q(execution_id=execution_id)
        )
