import logging

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.versioning import URLPathVersioning

from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.serializers import WorkflowExecutionSerializer

logger = logging.getLogger(__name__)


class WorkflowExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowExecutionSerializer

    CREATED_AT_FIELD_DESC = "-created_at"

    def get_queryset(self):
        # Get the uuid:pk from the URL path
        workflow_id = self.kwargs.get("pk")
        # ``IsOwner`` used to stand here, but it only implements
        # ``has_object_permission``, which DRF never invokes on ``list`` — the
        # same dead gate this PR removes from the log viewset. ``for_user`` is
        # the real one: without it any org member could enumerate every
        # execution of a workflow never shared with them (UN-2651).
        queryset = (
            WorkflowExecution.objects.for_user(self.request.user)
            .filter(workflow_id=workflow_id)
            .order_by(self.CREATED_AT_FIELD_DESC)
        )
        return queryset
