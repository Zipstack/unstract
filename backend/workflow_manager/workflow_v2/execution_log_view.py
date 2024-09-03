import logging

from permissions.permission import IsOwner
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.pagination import CustomPagination
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog
from workflow_manager.workflow_v2.serializers import WorkflowExecutionLogSerializer

logger = logging.getLogger(__name__)


class WorkflowExecutionLogViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    serializer_class = WorkflowExecutionLogSerializer
    pagination_class = CustomPagination

    EVENT_TIME_FELID_ASC = "event_time"

    def get_queryset(self):
        # Get the execution_id:pk from the URL path
        execution_id = self.kwargs.get("pk")
        queryset = ExecutionLog.objects.filter(execution_id=execution_id).order_by(
            self.EVENT_TIME_FELID_ASC
        )
        return queryset
