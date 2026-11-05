import logging

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated
from utils.filters.ordering_filter import DeterministicOrderingFilter
from utils.pagination import CustomPagination

from workflow_manager.execution.filter import (
    STUCK_PARAM,
    ExecutionFilter,
    stuck_requested,
)
from workflow_manager.execution.serializer import ExecutionSerializer
from workflow_manager.execution.serializer.stuck_abort import StuckExecutionSerializer
from workflow_manager.workflow_v2.models import WorkflowExecution

logger = logging.getLogger(__name__)


class UserWorkflowExecutionPermission(BasePermission):
    """Permission class that only allows users to see executions of workflows they created.

    This class controls access at the object level, determining if a user can view
    a specific execution based on workflow ownership.
    """

    def has_permission(self, request, view):
        # Allow access to the view itself
        # object-level permissions will filter individual items
        return True

    def has_object_permission(self, request, view, obj):
        # Check if this specific execution belongs to a workflow created by the user
        return WorkflowExecution.objects.for_user(request.user).filter(id=obj.id).exists()


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                STUCK_PARAM,
                OpenApiTypes.BOOL,
                description=(
                    "true: only PENDING/EXECUTING runs with no activity for longer "
                    "than the stuck threshold; each row then also carries "
                    "stuck_since. See execution/README.md."
                ),
            )
        ]
    )
)
class ExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, UserWorkflowExecutionPermission]
    serializer_class = ExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, DeterministicOrderingFilter]
    ordering_fields = ["created_at", "execution_time"]
    ordering = ["-created_at"]
    filterset_class = ExecutionFilter

    def get_queryset(self):
        # Use the custom manager method to filter executions for the current user
        return WorkflowExecution.objects.for_user(self.request.user)

    def get_serializer_class(self) -> type[ExecutionSerializer]:
        # Only ?stuck=true rows carry the stuck_since annotation.
        request = getattr(self, "request", None)
        if request is not None and stuck_requested(request.query_params):
            return StuckExecutionSerializer
        return ExecutionSerializer
