import logging

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.pagination import CustomPagination

from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.permissions import IsWorkflowOwnerOrShared
from workflow_manager.workflow_v2.serializers import FileHistorySerializer

logger = logging.getLogger(__name__)

MAX_BULK_DELETE_LIMIT = 100


class FileHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for file history operations with filtering support."""

    serializer_class = FileHistorySerializer
    lookup_field = "id"
    permission_classes = [IsAuthenticated, IsWorkflowOwnerOrShared]
    pagination_class = CustomPagination

    def _validate_execution_count(self, value, param_name):
        """Validate execution count parameter is a non-negative integer.

        Args:
            value: The value to validate
            param_name: Name of the parameter for error messages

        Returns:
            int: The validated integer value

        Raises:
            ValidationError: If value is invalid
        """
        try:
            int_value = int(value)
            if int_value < 0:
                raise ValidationError({param_name: "Must be a non-negative integer"})
            return int_value
        except (ValueError, TypeError):
            raise ValidationError({param_name: "Must be a valid integer"})

    def get_queryset(self):
        """Get file histories for workflow with filters."""
        # Reuse cached workflow from permission check
        if hasattr(self.request, "_workflow_cache"):
            workflow = self.request._workflow_cache
        else:
            # Fallback if permission didn't run (shouldn't happen)
            workflow_id = self.kwargs.get("workflow_id")
            workflow = get_object_or_404(Workflow, id=workflow_id)

        queryset = FileHistory.objects.filter(workflow=workflow)

        # Apply simple filters from query parameters
        status_param = self.request.query_params.get("status")
        if status_param:
            status_list = [s.strip() for s in status_param.split(",")]
            queryset = queryset.filter(status__in=status_list)

        exec_min = self.request.query_params.get("execution_count_min")
        if exec_min:
            exec_min_val = self._validate_execution_count(exec_min, "execution_count_min")
            queryset = queryset.filter(execution_count__gte=exec_min_val)

        exec_max = self.request.query_params.get("execution_count_max")
        if exec_max:
            exec_max_val = self._validate_execution_count(exec_max, "execution_count_max")
            queryset = queryset.filter(execution_count__lte=exec_max_val)

        file_path_param = self.request.query_params.get("file_path")
        if file_path_param:
            # Support partial matching (case-insensitive)
            queryset = queryset.filter(file_path__icontains=file_path_param)

        return queryset.order_by("-created_at")

    def destroy(self, request, workflow_id=None, id=None):
        """Delete single file history by ID."""
        file_history = self.get_object()
        file_history_id = file_history.id

        file_history.delete()

        logger.info(f"Deleted file history {file_history_id} for workflow {workflow_id}")

        return Response(
            {"message": "File history deleted successfully"}, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"])
    def clear(self, request, workflow_id=None):
        """Clear file histories with filters or by specific IDs.

        Supports two modes:
        1. ID-based deletion: Pass {"ids": [...]} to delete specific records (max 100)
        2. Filter-based deletion: Pass filters like status, execution_count_min, etc.

        At least one filter or IDs must be provided to prevent accidental deletion
        of all records.
        """
        # Extract all filter parameters upfront
        ids = request.data.get("ids", [])
        status_list = request.data.get("status", [])
        exec_min = request.data.get("execution_count_min")
        exec_max = request.data.get("execution_count_max")
        file_path_param = request.data.get("file_path")

        # Safeguard: require at least one filter or IDs to prevent accidental mass deletion
        has_criteria = bool(
            ids
            or status_list
            or exec_min is not None
            or exec_max is not None
            or file_path_param
        )
        if not has_criteria:
            return Response(
                {
                    "error": "At least one filter (ids, status, execution_count_min, "
                    "execution_count_max, or file_path) must be provided"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        workflow = get_object_or_404(Workflow, id=workflow_id)
        queryset = FileHistory.objects.filter(workflow=workflow)

        # Check for ID-based deletion
        if ids:
            if len(ids) > MAX_BULK_DELETE_LIMIT:
                return Response(
                    {
                        "error": f"Cannot delete more than {MAX_BULK_DELETE_LIMIT} "
                        f"items at once. Received {len(ids)} IDs."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(id__in=ids)
        else:
            # Apply filters from request body (filter-based deletion)
            if status_list:
                queryset = queryset.filter(status__in=status_list)

            if exec_min is not None:
                exec_min_val = self._validate_execution_count(
                    exec_min, "execution_count_min"
                )
                queryset = queryset.filter(execution_count__gte=exec_min_val)

            if exec_max is not None:
                exec_max_val = self._validate_execution_count(
                    exec_max, "execution_count_max"
                )
                queryset = queryset.filter(execution_count__lte=exec_max_val)

            if file_path_param:
                queryset = queryset.filter(file_path__icontains=file_path_param)

        deleted_count, _ = queryset.delete()

        logger.info(
            f"Cleared {deleted_count} file history records for workflow {workflow_id}"
        )

        return Response(
            {
                "deleted_count": deleted_count,
                "message": f"{deleted_count} file history records deleted",
            }
        )
