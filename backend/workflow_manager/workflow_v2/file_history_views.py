import logging

from django.conf import settings
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

        # Clear Redis cache for this file before deletion
        self._clear_cache_for_file(workflow_id, file_history)

        file_history.delete()

        logger.info(f"Deleted file history {file_history_id} for workflow {workflow_id}")

        return Response(
            {"message": "File history deleted successfully"}, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"])
    def clear(self, request, workflow_id=None):
        """Clear file histories with filters (direct delete)."""
        workflow = get_object_or_404(Workflow, id=workflow_id)
        queryset = FileHistory.objects.filter(workflow=workflow)

        # Apply filters from request body
        status_list = request.data.get("status", [])
        if status_list:
            queryset = queryset.filter(status__in=status_list)

        exec_min = request.data.get("execution_count_min")
        if exec_min is not None:
            exec_min_val = self._validate_execution_count(exec_min, "execution_count_min")
            queryset = queryset.filter(execution_count__gte=exec_min_val)

        exec_max = request.data.get("execution_count_max")
        if exec_max is not None:
            exec_max_val = self._validate_execution_count(exec_max, "execution_count_max")
            queryset = queryset.filter(execution_count__lte=exec_max_val)

        file_path_param = request.data.get("file_path")
        if file_path_param:
            queryset = queryset.filter(file_path__icontains=file_path_param)

        deleted_count, _ = queryset.delete()

        # Clear Redis cache pattern for workflow
        self._clear_workflow_cache(workflow_id)

        logger.info(
            f"Cleared {deleted_count} file history records for workflow {workflow_id}"
        )

        return Response(
            {
                "deleted_count": deleted_count,
                "message": f"{deleted_count} file history records deleted",
            }
        )

    def _clear_cache_for_file(self, workflow_id, file_history):
        """Clear Redis cache for specific file."""
        try:
            from workflow_manager.workflow_v2.execution.active_file_manager import (
                ActiveFileManager,
            )

            cache_key = ActiveFileManager._create_cache_key(
                workflow_id, file_history.provider_file_uuid, file_history.file_path
            )
            DB = settings.FILE_ACTIVE_CACHE_REDIS_DB
            from utils.cache import CacheService

            CacheService.delete_key(cache_key, db=DB)
            logger.debug(f"Cleared cache for file: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to clear cache for file: {e}")

    def _clear_workflow_cache(self, workflow_id):
        """Clear all Redis cache for workflow."""
        try:
            pattern = f"file_active:{workflow_id}:*"
            DB = settings.FILE_ACTIVE_CACHE_REDIS_DB
            from utils.cache import CacheService

            CacheService.clear_cache_optimized(pattern, db=DB)
            logger.debug(f"Cleared cache pattern: {pattern}")
        except Exception as e:
            logger.warning(f"Failed to clear workflow cache: {e}")
