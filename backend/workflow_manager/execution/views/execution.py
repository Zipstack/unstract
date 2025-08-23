import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import BasePermission, IsAuthenticated
from utils.pagination import CustomPagination

from workflow_manager.execution.filter import ExecutionFilter
from workflow_manager.execution.serializer import ExecutionSerializer
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


class ExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, UserWorkflowExecutionPermission]
    serializer_class = ExecutionSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "execution_time"]
    ordering = ["-created_at"]
    filterset_class = ExecutionFilter
    queryset = WorkflowExecution.objects.all()

    def get_queryset(self):
        # Use the custom manager method to filter executions for the current user
        return WorkflowExecution.objects.for_user(self.request.user)
