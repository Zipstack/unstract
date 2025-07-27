"""Internal API Views for File Execution
Handles file execution related endpoints for internal services.
"""

import logging

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.organization_utils import filter_queryset_by_organization

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.file_execution.models import WorkflowFileExecution

# Import serializers from workflow_manager internal API
from workflow_manager.internal_serializers import (
    FileExecutionStatusUpdateSerializer,
    WorkflowFileExecutionSerializer,
)

logger = logging.getLogger(__name__)


class FileExecutionInternalViewSet(viewsets.ModelViewSet):
    """Internal API ViewSet for File Execution operations."""

    serializer_class = WorkflowFileExecutionSerializer
    lookup_field = "id"

    def get_queryset(self):
        """Get file executions filtered by organization context and query parameters."""
        queryset = WorkflowFileExecution.objects.all()

        # Filter through the relationship: WorkflowFileExecution -> WorkflowExecution -> Workflow -> Organization
        queryset = filter_queryset_by_organization(
            queryset, self.request, "workflow_execution__workflow__organization"
        )

        # Debug: Log initial queryset count after organization filtering
        org_filtered_count = queryset.count()
        logger.debug(
            f"After organization filtering: {org_filtered_count} file executions"
        )

        # Support filtering by query parameters for get-or-create operations
        execution_id = self.request.query_params.get("execution_id")
        file_hash = self.request.query_params.get("file_hash")
        provider_file_uuid = self.request.query_params.get("provider_file_uuid")
        workflow_id = self.request.query_params.get("workflow_id")
        file_path = self.request.query_params.get(
            "file_path"
        )  # CRITICAL: Add file_path parameter

        logger.debug(
            f"Query parameters: execution_id={execution_id}, file_hash={file_hash}, provider_file_uuid={provider_file_uuid}, workflow_id={workflow_id}, file_path={file_path}"
        )

        # Apply filters step by step with debugging
        if execution_id:
            queryset = queryset.filter(workflow_execution_id=execution_id)
            logger.debug(f"After execution_id filter: {queryset.count()} file executions")

        # CRITICAL FIX: Include file_path filter to match unique constraints
        if file_path:
            queryset = queryset.filter(file_path=file_path)
            logger.debug(f"After file_path filter: {queryset.count()} file executions")

        # CRITICAL FIX: Match backend manager logic - use file_hash OR provider_file_uuid (not both)
        if file_hash:
            queryset = queryset.filter(file_hash=file_hash)
            logger.debug(f"After file_hash filter: {queryset.count()} file executions")
        elif provider_file_uuid:
            queryset = queryset.filter(provider_file_uuid=provider_file_uuid)
            logger.debug(
                f"After provider_file_uuid filter: {queryset.count()} file executions"
            )

        if workflow_id:
            queryset = queryset.filter(workflow_execution__workflow_id=workflow_id)
            logger.debug(f"After workflow_id filter: {queryset.count()} file executions")

        final_count = queryset.count()
        logger.info(
            f"Final queryset count: {final_count} file executions for params: execution_id={execution_id}, file_hash={file_hash}, provider_file_uuid={provider_file_uuid}, workflow_id={workflow_id}, file_path={file_path}"
        )

        # If we still have too many results, something is wrong with the filtering
        if final_count > 10:  # Reasonable threshold
            logger.warning(
                f"Query returned {final_count} file executions - filtering may not be working correctly"
            )
            logger.warning(
                f"Query params: execution_id={execution_id}, file_hash={file_hash}, workflow_id={workflow_id}"
            )

        return queryset

    def list(self, request, *args, **kwargs):
        """List file executions with enhanced filtering validation."""
        queryset = self.get_queryset()
        count = queryset.count()

        # If we get too many results, it means the filtering failed
        if count > 50:  # Conservative threshold
            logger.error(
                f"GET request returned {count} file executions - this suggests broken query parameter filtering"
            )
            logger.error(f"Request query params: {dict(request.query_params)}")

            # For debugging, show a sample of what we're returning
            sample_ids = list(queryset.values_list("id", flat=True)[:5])
            logger.error(f"Sample file execution IDs: {sample_ids}")

            # Return error response instead of broken list
            return Response(
                {
                    "error": "Query returned too many results",
                    "detail": f"Expected 0-1 file executions but got {count}. Check query parameters.",
                    "count": count,
                    "query_params": dict(request.query_params),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Continue with normal list behavior for reasonable result counts
        logger.info(f"GET request successfully filtered to {count} file executions")
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def status(self, request, id=None):
        """Update file execution status."""
        try:
            # Get file execution by ID with organization filtering
            # Don't use self.get_object() as it applies query parameter filtering
            base_queryset = WorkflowFileExecution.objects.all()
            base_queryset = filter_queryset_by_organization(
                base_queryset, request, "workflow_execution__workflow__organization"
            )

            try:
                file_execution = base_queryset.get(id=id)
            except WorkflowFileExecution.DoesNotExist:
                logger.warning(f"WorkflowFileExecution {id} not found for status update")
                return Response(
                    {
                        "error": "WorkflowFileExecution not found",
                        "detail": f"No file execution record found with ID {id}",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = FileExecutionStatusUpdateSerializer(data=request.data)

            if serializer.is_valid():
                validated_data = serializer.validated_data

                # Update file execution using the model's update_status method
                file_execution.update_status(
                    status=validated_data["status"],
                    execution_error=validated_data.get("error_message"),
                    execution_time=validated_data.get("execution_time"),
                )

                logger.info(
                    f"Updated file execution {id} status to {validated_data['status']}"
                )

                # Return consistent dataclass response
                from unstract.core.data_models import FileExecutionStatusUpdateRequest

                response_data = FileExecutionStatusUpdateRequest(
                    status=file_execution.status,
                    error_message=file_execution.execution_error,
                    result=getattr(file_execution, "result", None),
                )

                return Response(
                    {
                        "status": "updated",
                        "file_execution_id": str(file_execution.id),
                        "data": response_data.to_dict(),
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Failed to update file execution status {id}: {str(e)}")
            return Response(
                {"error": "Failed to update file execution status", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def create(self, request, *args, **kwargs):
        """Create or get existing workflow file execution using existing manager method."""
        try:
            from workflow_manager.workflow_v2.models.execution import WorkflowExecution

            data = request.data
            execution_id = data.get("execution_id")
            file_hash_data = data.get("file_hash", {})
            workflow_id = data.get("workflow_id")

            if not execution_id:
                return Response(
                    {"error": "execution_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get workflow execution with organization filtering
            try:
                workflow_execution = WorkflowExecution.objects.get(id=execution_id)
                # Verify organization access
                filter_queryset_by_organization(
                    WorkflowExecution.objects.filter(id=execution_id),
                    request,
                    "workflow__organization",
                ).get()
            except WorkflowExecution.DoesNotExist:
                return Response(
                    {"error": "WorkflowExecution not found or access denied"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Convert request data to FileHash object that the manager expects
            file_hash = FileHash(
                file_path=file_hash_data.get("file_path", ""),
                file_name=file_hash_data.get("file_name", ""),
                source_connection_type=file_hash_data.get("source_connection_type", ""),
                file_hash=file_hash_data.get("file_hash"),
                file_size=file_hash_data.get("file_size"),
                provider_file_uuid=file_hash_data.get("provider_file_uuid"),
                mime_type=file_hash_data.get("mime_type"),
                fs_metadata=file_hash_data.get("fs_metadata"),
                file_destination=file_hash_data.get("file_destination"),
                is_executed=file_hash_data.get("is_executed", False),
                file_number=file_hash_data.get("file_number"),
            )

            # Determine if this is an API request (affects file_path handling in manager)
            is_api = file_hash_data.get("source_connection_type", "") == "API"

            # Use existing manager method - this handles get_or_create logic properly
            file_execution = WorkflowFileExecution.objects.get_or_create_file_execution(
                workflow_execution=workflow_execution, file_hash=file_hash, is_api=is_api
            )

            # Return single object (not list!) using serializer
            serializer = self.get_serializer(file_execution)
            response_data = serializer.data

            # ROOT CAUSE FIX: Ensure file_path is always present in API response
            # The backend model sets file_path to None for API files, but workers require it
            if not response_data.get("file_path") and file_hash.file_path:
                logger.info(
                    f"Backend stored null file_path for API file, including original: {file_hash.file_path}"
                )
                response_data["file_path"] = file_hash.file_path

            logger.info(
                f"Retrieved/created file execution {file_execution.id} for workflow {workflow_id}"
            )
            logger.debug(f"Response data: {response_data}")

            # Determine status code based on whether it was created or retrieved
            # Note: We can't easily tell if it was created or retrieved from the manager,
            # but 201 is fine for both cases in this context
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Failed to get/create file execution: {str(e)}")
            return Response(
                {"error": "Failed to get/create file execution", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["patch"])
    def update_hash(self, request, id=None):
        """Update file execution with computed file hash."""
        try:
            # Get file execution by ID with organization filtering
            base_queryset = WorkflowFileExecution.objects.all()
            base_queryset = filter_queryset_by_organization(
                base_queryset, request, "workflow_execution__workflow__organization"
            )

            try:
                file_execution = base_queryset.get(id=id)
            except WorkflowFileExecution.DoesNotExist:
                logger.warning(f"WorkflowFileExecution {id} not found for hash update")
                return Response(
                    {
                        "error": "WorkflowFileExecution not found",
                        "detail": f"No file execution record found with ID {id}",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Extract update data
            file_hash = request.data.get("file_hash")
            fs_metadata = request.data.get("fs_metadata")

            if not file_hash and not fs_metadata:
                return Response(
                    {"error": "file_hash or fs_metadata is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Use the model's update method for efficient field-specific updates
            file_execution.update(file_hash=file_hash, fs_metadata=fs_metadata)

            logger.info(
                f"Updated file execution {id} with file_hash: {file_hash[:16] if file_hash else 'none'}..."
            )

            # Return updated record
            serializer = self.get_serializer(file_execution)
            return Response(
                {
                    "status": "updated",
                    "file_execution_id": str(file_execution.id),
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Failed to update file execution hash {id}: {str(e)}")
            return Response(
                {"error": "Failed to update file execution hash", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileExecutionBatchCreateAPIView(APIView):
    """Internal API endpoint for creating multiple file executions in a single batch."""

    def post(self, request):
        """Create multiple file executions in a single batch request."""
        try:
            file_executions = request.data.get("file_executions", [])

            if not file_executions:
                return Response(
                    {"error": "file_executions list is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            successful_creations = []
            failed_creations = []

            with transaction.atomic():
                for file_execution_data in file_executions:
                    try:
                        from workflow_manager.workflow_v2.models.execution import (
                            WorkflowExecution,
                        )

                        execution_id = file_execution_data.get("execution_id")
                        file_hash_data = file_execution_data.get("file_hash", {})

                        if not execution_id:
                            failed_creations.append(
                                {
                                    "file_name": file_hash_data.get(
                                        "file_name", "unknown"
                                    ),
                                    "error": "execution_id is required",
                                }
                            )
                            continue

                        # Get workflow execution with organization filtering
                        try:
                            workflow_execution = WorkflowExecution.objects.get(
                                id=execution_id
                            )
                            # Verify organization access
                            filter_queryset_by_organization(
                                WorkflowExecution.objects.filter(id=execution_id),
                                request,
                                "workflow__organization",
                            ).get()
                        except WorkflowExecution.DoesNotExist:
                            failed_creations.append(
                                {
                                    "file_name": file_hash_data.get(
                                        "file_name", "unknown"
                                    ),
                                    "error": "WorkflowExecution not found or access denied",
                                }
                            )
                            continue

                        # Convert request data to FileHash object
                        file_hash = FileHash(
                            file_path=file_hash_data.get("file_path", ""),
                            file_name=file_hash_data.get("file_name", ""),
                            source_connection_type=file_hash_data.get(
                                "source_connection_type", ""
                            ),
                            file_hash=file_hash_data.get("file_hash"),
                            file_size=file_hash_data.get("file_size"),
                            provider_file_uuid=file_hash_data.get("provider_file_uuid"),
                            mime_type=file_hash_data.get("mime_type"),
                            fs_metadata=file_hash_data.get("fs_metadata"),
                            file_destination=file_hash_data.get("file_destination"),
                            is_executed=file_hash_data.get("is_executed", False),
                            file_number=file_hash_data.get("file_number"),
                        )

                        # Determine if this is an API request
                        is_api = file_hash_data.get("source_connection_type", "") == "API"

                        # Use existing manager method
                        file_execution = (
                            WorkflowFileExecution.objects.get_or_create_file_execution(
                                workflow_execution=workflow_execution,
                                file_hash=file_hash,
                                is_api=is_api,
                            )
                        )

                        # ROOT CAUSE FIX: Ensure file_path is always present in batch response
                        # The backend model sets file_path to None for API files, but workers require it
                        response_file_path = file_execution.file_path
                        if not response_file_path and file_hash.file_path:
                            response_file_path = file_hash.file_path

                        successful_creations.append(
                            {
                                "id": str(file_execution.id),
                                "file_name": file_execution.file_name,
                                "file_path": response_file_path,
                                "status": file_execution.status,
                            }
                        )

                    except Exception as e:
                        failed_creations.append(
                            {
                                "file_name": file_execution_data.get("file_hash", {}).get(
                                    "file_name", "unknown"
                                ),
                                "error": str(e),
                            }
                        )

            logger.info(
                f"Batch file execution creation: {len(successful_creations)} successful, {len(failed_creations)} failed"
            )

            return Response(
                {
                    "successful_creations": successful_creations,
                    "failed_creations": failed_creations,
                    "total_processed": len(file_executions),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Failed to process batch file execution creation: {str(e)}")
            return Response(
                {
                    "error": "Failed to process batch file execution creation",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileExecutionBatchStatusUpdateAPIView(APIView):
    """Internal API endpoint for updating multiple file execution statuses in a single batch."""

    def post(self, request):
        """Update multiple file execution statuses in a single batch request."""
        try:
            status_updates = request.data.get("status_updates", [])

            if not status_updates:
                return Response(
                    {"error": "status_updates list is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            successful_updates = []
            failed_updates = []

            with transaction.atomic():
                for update_data in status_updates:
                    try:
                        file_execution_id = update_data.get("file_execution_id")
                        status_value = update_data.get("status")

                        if not file_execution_id or not status_value:
                            failed_updates.append(
                                {
                                    "file_execution_id": file_execution_id,
                                    "error": "file_execution_id and status are required",
                                }
                            )
                            continue

                        # Get file execution with organization filtering
                        base_queryset = WorkflowFileExecution.objects.all()
                        base_queryset = filter_queryset_by_organization(
                            base_queryset,
                            request,
                            "workflow_execution__workflow__organization",
                        )

                        try:
                            file_execution = base_queryset.get(id=file_execution_id)
                        except WorkflowFileExecution.DoesNotExist:
                            failed_updates.append(
                                {
                                    "file_execution_id": file_execution_id,
                                    "error": "WorkflowFileExecution not found",
                                }
                            )
                            continue

                        # Update file execution using the model's update_status method
                        file_execution.update_status(
                            status=status_value,
                            execution_error=update_data.get("error_message"),
                            execution_time=update_data.get("execution_time"),
                        )

                        successful_updates.append(
                            {
                                "file_execution_id": str(file_execution.id),
                                "status": file_execution.status,
                                "file_name": file_execution.file_name,
                            }
                        )

                    except Exception as e:
                        failed_updates.append(
                            {"file_execution_id": file_execution_id, "error": str(e)}
                        )

            logger.info(
                f"Batch file execution status update: {len(successful_updates)} successful, {len(failed_updates)} failed"
            )

            return Response(
                {
                    "successful_updates": successful_updates,
                    "failed_updates": failed_updates,
                    "total_processed": len(status_updates),
                }
            )

        except Exception as e:
            logger.error(
                f"Failed to process batch file execution status update: {str(e)}"
            )
            return Response(
                {
                    "error": "Failed to process batch file execution status update",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileExecutionBatchHashUpdateAPIView(APIView):
    """Internal API endpoint for updating multiple file execution hashes in a single batch."""

    def post(self, request):
        """Update multiple file execution hashes in a single batch request."""
        try:
            hash_updates = request.data.get("hash_updates", [])

            if not hash_updates:
                return Response(
                    {"error": "hash_updates list is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            successful_updates = []
            failed_updates = []

            with transaction.atomic():
                for update_data in hash_updates:
                    try:
                        file_execution_id = update_data.get("file_execution_id")
                        file_hash = update_data.get("file_hash")

                        if not file_execution_id or not file_hash:
                            failed_updates.append(
                                {
                                    "file_execution_id": file_execution_id,
                                    "error": "file_execution_id and file_hash are required",
                                }
                            )
                            continue

                        # Get file execution with organization filtering
                        base_queryset = WorkflowFileExecution.objects.all()
                        base_queryset = filter_queryset_by_organization(
                            base_queryset,
                            request,
                            "workflow_execution__workflow__organization",
                        )

                        try:
                            file_execution = base_queryset.get(id=file_execution_id)
                        except WorkflowFileExecution.DoesNotExist:
                            failed_updates.append(
                                {
                                    "file_execution_id": file_execution_id,
                                    "error": "WorkflowFileExecution not found",
                                }
                            )
                            continue

                        # Update file execution hash using the model's update method
                        file_execution.update(
                            file_hash=file_hash,
                            fs_metadata=update_data.get("fs_metadata"),
                        )

                        successful_updates.append(
                            {
                                "file_execution_id": str(file_execution.id),
                                "file_hash": file_hash[:16] + "..."
                                if file_hash
                                else None,
                                "file_name": file_execution.file_name,
                            }
                        )

                    except Exception as e:
                        failed_updates.append(
                            {"file_execution_id": file_execution_id, "error": str(e)}
                        )

            logger.info(
                f"Batch file execution hash update: {len(successful_updates)} successful, {len(failed_updates)} failed"
            )

            return Response(
                {
                    "successful_updates": successful_updates,
                    "failed_updates": failed_updates,
                    "total_processed": len(hash_updates),
                }
            )

        except Exception as e:
            logger.error(f"Failed to process batch file execution hash update: {str(e)}")
            return Response(
                {
                    "error": "Failed to process batch file execution hash update",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileExecutionMetricsAPIView(APIView):
    """Internal API endpoint for getting file execution metrics."""

    def get(self, request):
        """Get file execution metrics with optional filtering."""
        try:
            # Get query parameters
            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")
            workflow_id = request.query_params.get("workflow_id")
            execution_id = request.query_params.get("execution_id")
            status = request.query_params.get("status")

            # Build base queryset with organization filtering
            file_executions = WorkflowFileExecution.objects.all()
            file_executions = filter_queryset_by_organization(
                file_executions, request, "workflow_execution__workflow__organization"
            )

            # Apply filters
            if start_date:
                from datetime import datetime

                file_executions = file_executions.filter(
                    created_at__gte=datetime.fromisoformat(start_date)
                )
            if end_date:
                from datetime import datetime

                file_executions = file_executions.filter(
                    created_at__lte=datetime.fromisoformat(end_date)
                )
            if workflow_id:
                file_executions = file_executions.filter(
                    workflow_execution__workflow_id=workflow_id
                )
            if execution_id:
                file_executions = file_executions.filter(
                    workflow_execution_id=execution_id
                )
            if status:
                file_executions = file_executions.filter(status=status)

            # Calculate metrics
            from django.db.models import Avg, Count, Sum

            total_file_executions = file_executions.count()

            # Status breakdown
            status_counts = file_executions.values("status").annotate(count=Count("id"))
            status_breakdown = {item["status"]: item["count"] for item in status_counts}

            # Success rate
            completed_count = status_breakdown.get("COMPLETED", 0)
            success_rate = (
                (completed_count / total_file_executions)
                if total_file_executions > 0
                else 0
            )

            # Average execution time
            avg_execution_time = (
                file_executions.aggregate(avg_time=Avg("execution_time"))["avg_time"] or 0
            )

            # File size statistics
            total_file_size = (
                file_executions.aggregate(total_size=Sum("file_size"))["total_size"] or 0
            )

            avg_file_size = (
                file_executions.aggregate(avg_size=Avg("file_size"))["avg_size"] or 0
            )

            metrics = {
                "total_file_executions": total_file_executions,
                "status_breakdown": status_breakdown,
                "success_rate": success_rate,
                "average_execution_time": avg_execution_time,
                "total_file_size": total_file_size,
                "average_file_size": avg_file_size,
                "filters_applied": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "workflow_id": workflow_id,
                    "execution_id": execution_id,
                    "status": status,
                },
            }

            logger.info(
                f"Generated file execution metrics: {total_file_executions} executions, {success_rate:.2%} success rate"
            )

            return Response(metrics)

        except Exception as e:
            logger.error(f"Failed to get file execution metrics: {str(e)}")
            return Response(
                {"error": "Failed to get file execution metrics", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
