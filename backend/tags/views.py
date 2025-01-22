from django_filters.rest_framework import DjangoFilterBackend
from permissions.permission import IsOrganizationMember
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from tags.helper import TagHelper
from tags.models import Tag
from tags.serializers import TagSerializer
from utils.pagination import CustomPagination
from utils.user_context import UserContext
from workflow_manager.file_execution.serializers import WorkflowFileExecutionSerializer
from workflow_manager.workflow_v2.serializers import WorkflowExecutionSerializer


class TagViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    serializer_class = TagSerializer
    pagination_class = CustomPagination
    ordering_fields = ["created_at"]
    filter_backends = [DjangoFilterBackend, OrderingFilter]

    def get_queryset(self):
        """
        Returns a queryset filtered by the current user's organization.
        """
        user_organization = UserContext.get_organization()
        return Tag.objects.filter(organization=user_organization)

    @action(detail=True, methods=["get"], url_path="workflow-executions")
    def workflow_executions(self, request, pk=None):
        """
        Custom action to list all WorkflowExecution instances associated
        with a specific Tag.
        """
        try:
            tag = self.get_object()  # Fetch the tag based on the primary key
            workflow_executions = TagHelper.list_workflow_executions(tag=tag)

            # Apply pagination
            page = self.paginate_queryset(workflow_executions)
            if page is not None:
                serializer = WorkflowExecutionSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = WorkflowExecutionSerializer(workflow_executions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Tag.DoesNotExist:
            return Response(
                {"detail": "Tag not found."}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["get"], url_path="workflow-file-executions")
    def workflow_file_executions(self, request, pk=None):
        """
        Custom action to list all WorkflowFileExecution instances associated
        with a specific Tag.
        """
        try:
            tag = self.get_object()  # Get the tag based on the primary key
            workflow_file_executions = TagHelper.list_workflow_file_executions(tag=tag)
            # Apply pagination
            page = self.paginate_queryset(workflow_file_executions)
            if page is not None:
                serializer = WorkflowFileExecutionSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = WorkflowFileExecutionSerializer(
                workflow_file_executions, many=True
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Tag.DoesNotExist:
            return Response(
                {"detail": "Tag not found."}, status=status.HTTP_404_NOT_FOUND
            )
