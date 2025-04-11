import logging

from permissions.permission import IsOwner
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning

from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.serializers import WorkflowExecutionSerializer

logger = logging.getLogger(__name__)


class WorkflowExecutionViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    serializer_class = WorkflowExecutionSerializer

    CREATED_AT_FIELD_DESC = "-created_at"

    def get_queryset(self):
        # Get the uuid:pk from the URL path
        workflow_id = self.kwargs.get("pk")
        queryset = WorkflowExecution.objects.filter(workflow_id=workflow_id).order_by(
            self.CREATED_AT_FIELD_DESC
        )
        return queryset
