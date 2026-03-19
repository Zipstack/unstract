import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from permissions.permission import IsOwner
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning

from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.serializers import WorkflowExecutionSerializer

logger = logging.getLogger(__name__)


@extend_schema_view(
    retrieve=extend_schema(
        summary="Get workflow execution details",
        description="Returns execution status, result, and metadata for a single execution.",
        tags=["Workflows"],
    ),
    list=extend_schema(
        summary="List executions for a workflow",
        description="Returns paginated execution history for a specific workflow, "
        "ordered by most recent first.",
        tags=["Workflows"],
    ),
)
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
