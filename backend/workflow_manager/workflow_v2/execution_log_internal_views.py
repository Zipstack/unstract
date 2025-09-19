"""Internal API Views for Execution Log Operations

These views handle internal API requests from workers for execution log operations.
They provide database access while keeping business logic in workers.
"""

import logging
from collections import defaultdict

from django.db import transaction
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.cache_service import CacheService
from utils.constants import ExecutionLogConstants
from utils.dto import LogDataDTO

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models import ExecutionLog, WorkflowExecution

logger = logging.getLogger(__name__)


class BulkCreateExecutionLogsAPIView(APIView):
    """API view for bulk creating execution logs via internal API."""

    def post(self, request: Request) -> Response:
        """Create execution logs in bulk.

        Args:
            request: HTTP request containing logs data

        Returns:
            JSON response with creation results
        """
        try:
            logs_data = request.data.get("logs", [])

            if not logs_data:
                return Response(
                    {"error": "No logs data provided"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Group logs by organization and validate
            organization_logs = defaultdict(list)
            execution_ids = set()
            file_execution_ids = set()

            for log_data in logs_data:
                execution_id = log_data.get("execution_id")
                organization_id = log_data.get("organization_id")

                if not execution_id or not organization_id:
                    continue

                execution_ids.add(execution_id)
                if log_data.get("file_execution_id"):
                    file_execution_ids.add(log_data["file_execution_id"])

            # Preload execution objects
            execution_map = {
                str(obj.id): obj
                for obj in WorkflowExecution.objects.filter(id__in=execution_ids)
            }
            file_execution_map = {
                str(obj.id): obj
                for obj in WorkflowFileExecution.objects.filter(id__in=file_execution_ids)
            }

            # Create execution log objects
            execution_logs_to_create = []
            for log_data in logs_data:
                execution_id = log_data.get("execution_id")
                organization_id = log_data.get("organization_id")

                if not execution_id or not organization_id:
                    continue

                execution = execution_map.get(execution_id)
                if not execution:
                    continue

                execution_log = ExecutionLog(
                    wf_execution=execution,
                    data=log_data.get("data", {}),
                    event_time=log_data.get("event_time"),
                )

                if log_data.get("file_execution_id"):
                    file_execution = file_execution_map.get(log_data["file_execution_id"])
                    if file_execution:
                        execution_log.file_execution = file_execution

                execution_logs_to_create.append(execution_log)
                organization_logs[organization_id].append(execution_log)

            # Bulk create logs
            created_count = 0
            with transaction.atomic():
                if execution_logs_to_create:
                    ExecutionLog.objects.bulk_create(
                        execution_logs_to_create, ignore_conflicts=True
                    )
                    created_count = len(execution_logs_to_create)

            return Response(
                {
                    "created_count": created_count,
                    "total_logs": len(logs_data),
                    "organizations_processed": len(organization_logs),
                }
            )

        except Exception as e:
            logger.error(f"Error creating execution logs in bulk: {e}", exc_info=True)
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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


class GetCacheLogBatchAPIView(APIView):
    """API view for getting a batch of logs from Redis cache."""

    def post(self, request: Request) -> Response:
        """Get a batch of logs from Redis cache.

        Args:
            request: HTTP request containing queue name and batch limit

        Returns:
            JSON response with log data
        """
        try:
            queue_name = request.data.get(
                "queue_name", ExecutionLogConstants.LOG_QUEUE_NAME
            )
            batch_limit = request.data.get(
                "batch_limit", ExecutionLogConstants.LOGS_BATCH_LIMIT
            )

            logs_data = []
            logs_count = 0

            # Collect logs from cache (batch retrieval)
            while logs_count < batch_limit:
                log = CacheService.lpop(queue_name)
                if not log:
                    break

                log_data_dto: LogDataDTO | None = LogDataDTO.from_json(log)
                if log_data_dto:
                    # Convert to dictionary for JSON serialization
                    log_dict = {
                        "execution_id": log_data_dto.execution_id,
                        "organization_id": log_data_dto.organization_id,
                        "file_execution_id": log_data_dto.file_execution_id,
                        "data": log_data_dto.data,
                        "event_time": log_data_dto.event_time.isoformat()
                        if log_data_dto.event_time
                        else None,
                    }
                    logs_data.append(log_dict)
                    logs_count += 1

            return Response(
                {
                    "logs": logs_data,
                    "count": logs_count,
                    "queue_name": queue_name,
                }
            )

        except Exception as e:
            logger.error(f"Error getting log batch from cache: {e}", exc_info=True)
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
