"""Internal API Views for Execution Log Operations

These views handle internal API requests from workers for execution log operations.
They provide database access while keeping business logic in workers.
"""

import logging

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.execution_log_utils import (
    process_log_history_from_cache,
)
from workflow_manager.workflow_v2.models import WorkflowExecution

logger = logging.getLogger(__name__)


class GetWorkflowExecutionsByIdsAPIView(APIView):
    """API view for getting workflow executions by IDs."""

    def post(self, request: Request) -> Response:
        """Get workflow execution data for given IDs.

        Args:
            request: HTTP request containing execution IDs

        Returns:
            JSON response with execution data
        """
        try:
            execution_ids = request.data.get("execution_ids", [])

            executions = WorkflowExecution.objects.filter(id__in=execution_ids)
            execution_data = {}

            for execution in executions:
                execution_data[str(execution.id)] = {
                    "id": str(execution.id),
                    "workflow_id": str(execution.workflow.id)
                    if execution.workflow
                    else None,
                    "status": execution.status,
                    "created_at": execution.created_at.isoformat()
                    if execution.created_at
                    else None,
                }

            return Response({"executions": execution_data})

        except Exception as e:
            logger.error(f"Error getting workflow executions: {e}", exc_info=True)
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GetFileExecutionsByIdsAPIView(APIView):
    """API view for getting file executions by IDs."""

    def post(self, request: Request) -> Response:
        """Get file execution data for given IDs.

        Args:
            request: HTTP request containing file execution IDs

        Returns:
            JSON response with file execution data
        """
        try:
            file_execution_ids = request.data.get("file_execution_ids", [])

            file_executions = WorkflowFileExecution.objects.filter(
                id__in=file_execution_ids
            )
            file_execution_data = {}

            for file_execution in file_executions:
                file_execution_data[str(file_execution.id)] = {
                    "id": str(file_execution.id),
                    "workflow_execution_id": str(file_execution.workflow_execution.id)
                    if file_execution.workflow_execution
                    else None,
                    "status": file_execution.status,
                    "created_at": file_execution.created_at.isoformat()
                    if file_execution.created_at
                    else None,
                }

            return Response({"file_executions": file_execution_data})

        except Exception as e:
            logger.error(f"Error getting file executions: {e}", exc_info=True)
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ValidateExecutionReferencesAPIView(APIView):
    """API view for validating execution references exist."""

    def post(self, request: Request) -> Response:
        """Validate that execution references exist.

        Args:
            request: HTTP request containing execution and file execution IDs

        Returns:
            JSON response with validation results
        """
        try:
            execution_ids = request.data.get("execution_ids", [])
            file_execution_ids = request.data.get("file_execution_ids", [])

            # Check which executions exist
            existing_executions = {
                str(obj.id)
                for obj in WorkflowExecution.objects.filter(id__in=execution_ids)
            }

            # Check which file executions exist
            existing_file_executions = {
                str(obj.id)
                for obj in WorkflowFileExecution.objects.filter(id__in=file_execution_ids)
            }

            return Response(
                {
                    "valid_executions": list(existing_executions),
                    "valid_file_executions": list(existing_file_executions),
                }
            )

        except Exception as e:
            logger.error(f"Error validating execution references: {e}", exc_info=True)
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProcessLogHistoryAPIView(APIView):
    """API view for processing log history from scheduler.

    This endpoint is called by the log history scheduler when logs exist in Redis queue.
    It reuses the existing business logic from execution_log_utils.process_log_history_from_cache().
    """

    def post(self, request: Request) -> Response:
        """Process log history batch from Redis cache.

        Args:
            request: HTTP request (no parameters needed)

        Returns:
            JSON response with processing results
        """
        try:
            # Reuse existing business logic (uses ExecutionLogConstants for config)
            result = process_log_history_from_cache()

            return Response(result)

        except Exception as e:
            logger.error(f"Error processing log history: {e}", exc_info=True)
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
