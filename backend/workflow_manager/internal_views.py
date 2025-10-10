"""Workflow Manager Internal API Views
Handles workflow execution related endpoints for internal services.
"""

import logging
import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from tool_instance_v2.models import ToolInstance
from utils.constants import Account
from utils.local_context import StateStore
from utils.organization_utils import filter_queryset_by_organization

# Import new dataclasses for WorkflowDefinitionAPIView
from unstract.core.data_models import (
    ConnectionType,
    ConnectorInstanceData,
    WorkflowDefinitionResponseData,
    WorkflowEndpointConfigData,
    WorkflowEndpointConfigResponseData,
)
from workflow_manager.endpoint_v2.endpoint_utils import WorkflowEndpointUtils
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from .internal_serializers import (
    FileBatchCreateSerializer,
    FileBatchResponseSerializer,
    WorkflowExecutionContextSerializer,
    WorkflowExecutionSerializer,
    WorkflowExecutionStatusUpdateSerializer,
)

logger = logging.getLogger(__name__)


class WorkflowExecutionInternalViewSet(viewsets.ReadOnlyModelViewSet):
    """Internal API ViewSet for Workflow Execution operations.
    Provides workflow execution CRUD operations for internal services.
    """

    serializer_class = WorkflowExecutionSerializer
    lookup_field = "id"

    def get_queryset(self):
        """Get workflow executions filtered by organization context."""
        queryset = WorkflowExecution.objects.select_related("workflow").prefetch_related(
            "tags"
        )
        return filter_queryset_by_organization(
            queryset, self.request, "workflow__organization"
        )

    def list(self, request, *args, **kwargs):
        """List workflow executions with proper query parameter filtering."""
        try:
            # Start with organization-filtered queryset
            queryset = self.get_queryset()

            # Apply query parameter filters
            workflow_id = request.query_params.get("workflow_id")
            if workflow_id:
                queryset = queryset.filter(workflow_id=workflow_id)

            status_filter = request.query_params.get("status__in")
            if status_filter:
                # Handle comma-separated status values
                statuses = [s.strip() for s in status_filter.split(",")]
                queryset = queryset.filter(status__in=statuses)

            # Apply any other filters
            status = request.query_params.get("status")
            if status:
                queryset = queryset.filter(status=status)

            # Order by creation time (newest first) for consistent results
            queryset = queryset.order_by("-created_at")

            # Serialize the filtered queryset
            serializer = self.get_serializer(queryset, many=True)

            logger.info(
                f"WorkflowExecution list: returned {len(serializer.data)} executions"
            )
            logger.debug(
                f"Applied filters - workflow_id: {workflow_id}, status__in: {status_filter}, status: {status}"
            )

            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error in WorkflowExecution list: {str(e)}")
            return Response(
                {"error": "Failed to list workflow executions", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def retrieve(self, request, *args, **kwargs):
        """Get specific workflow execution with context."""
        try:
            execution = self.get_object()

            # Check if cost data is requested (expensive operation)
            include_cost = request.GET.get("include_cost", "false").lower() == "true"
            file_execution = request.GET.get("file_execution", "true").lower() == "true"

            # Build comprehensive context
            workflow_definition = {}
            if execution.workflow:
                workflow_definition = {
                    "workflow_id": str(execution.workflow.id),
                    "workflow_name": execution.workflow.workflow_name,
                    "workflow_type": execution.workflow.deployment_type,
                    "description": execution.workflow.description,
                    "source_settings": execution.workflow.source_settings or {},
                    "destination_settings": execution.workflow.destination_settings or {},
                    "is_active": execution.workflow.is_active,
                    "status": execution.workflow.status,
                }

            context_data = {
                "execution": execution,  # Pass model instance, not serialized data
                "workflow_definition": workflow_definition,
                "source_config": self._get_source_config(execution),
                "destination_config": self._get_destination_config(execution),
                "organization_context": self._get_organization_context(execution),
                "file_executions": list(execution.file_executions.values())
                if file_execution
                else [],
            }

            # Only calculate cost if explicitly requested (expensive database operation)
            if include_cost:
                context_data["aggregated_usage_cost"] = execution.aggregated_usage_cost

            serializer = WorkflowExecutionContextSerializer(context_data)
            return Response(serializer.data)

        except Exception as e:
            logger.error(
                f"Failed to retrieve workflow execution {kwargs.get('id')}: {str(e)}"
            )
            return Response(
                {"error": "Failed to retrieve workflow execution", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_source_config(self, execution: WorkflowExecution) -> dict:
        """Get source configuration for execution with connector instance details."""
        try:
            workflow = execution.workflow
            if not workflow:
                logger.warning(f"No workflow found for execution {execution.id}")
                return {}

            # Get workflow-level source settings
            source_settings = {}
            workflow_type = "general_workflow"
            is_api = False

            if execution.pipeline_id:
                # Check if pipeline_id references a Pipeline or APIDeployment (like serializer)
                from api_v2.models import APIDeployment
                from pipeline_v2.models import Pipeline

                try:
                    # First check if it's a Pipeline
                    pipeline = Pipeline.objects.get(id=execution.pipeline_id)
                    source_settings = pipeline.workflow.source_settings or {}
                    workflow_type = "pipeline"
                    is_api = False
                    logger.debug(
                        f"Pipeline {execution.pipeline_id} source settings: {bool(source_settings)}"
                    )
                except Pipeline.DoesNotExist:
                    # Check if it's an APIDeployment (like serializer does)
                    try:
                        api_deployment = APIDeployment.objects.get(
                            id=execution.pipeline_id
                        )
                        source_settings = workflow.source_settings or {}
                        workflow_type = "api_deployment"
                        is_api = True
                        logger.debug(
                            f"APIDeployment {execution.pipeline_id} found for execution {execution.id}"
                        )
                    except APIDeployment.DoesNotExist:
                        # Neither Pipeline nor APIDeployment exists
                        logger.warning(
                            f"Neither Pipeline nor APIDeployment found for ID {execution.pipeline_id} in execution {execution.id}"
                        )
                        source_settings = workflow.source_settings or {}
                        workflow_type = "pipeline_not_found"
            else:
                # API deployment or general workflow execution
                source_settings = workflow.source_settings or {}
                if (
                    workflow
                    and hasattr(workflow, "api_deployments")
                    and workflow.api_deployments.filter(is_active=True).exists()
                ):
                    workflow_type = "api_deployment"
                    is_api = True
                logger.debug(
                    f"Workflow {workflow.id} source settings: {bool(source_settings)}"
                )

            # Get source connector instance from workflow endpoints
            from workflow_manager.endpoint_v2.models import WorkflowEndpoint

            source_connector_data = None
            try:
                # Look for source endpoint with connector instance
                source_endpoint = (
                    WorkflowEndpoint.objects.select_related("connector_instance")
                    .filter(
                        workflow=workflow,
                        endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
                    )
                    .first()
                )

                if source_endpoint and source_endpoint.connector_instance:
                    source_connector_instance = source_endpoint.connector_instance
                    source_connector_data = {
                        "connector_id": source_connector_instance.connector_id,
                        "connector_settings": source_connector_instance.metadata or {},
                        "connector_name": getattr(
                            source_connector_instance, "connector_name", ""
                        ),
                    }
                    logger.debug(
                        f"Found source connector instance: {source_connector_instance.connector_id}"
                    )

                    # Include endpoint configuration in source settings
                    if source_endpoint.configuration:
                        source_settings.update(source_endpoint.configuration)
                else:
                    logger.debug("No source connector instance found for workflow")

            except Exception as source_error:
                logger.warning(
                    f"Failed to get source connector info for workflow {workflow.id}: {str(source_error)}"
                )

            # Build comprehensive source config
            source_config = {
                "type": workflow_type,
                "source_settings": source_settings,
                "is_api": is_api,
            }

            # Add pipeline/deployment specific info
            if execution.pipeline_id and workflow_type != "pipeline_not_found":
                source_config["pipeline_id"] = str(execution.pipeline_id)
            elif workflow_type == "api_deployment":
                api_deployment = workflow.api_deployments.first()
                if api_deployment:
                    source_config["deployment_id"] = str(api_deployment.id)

            # Add source connector instance data if available
            if source_connector_data:
                source_config.update(source_connector_data)
                logger.debug("Added source connector instance data to source config")

            return source_config

        except Exception as e:
            logger.warning(
                f"Failed to get source config for execution {execution.id}: {str(e)}"
            )
            return {}

    def _get_destination_config(self, execution: WorkflowExecution) -> dict:
        """Get destination configuration for execution with connector instance details."""
        try:
            workflow = execution.workflow
            if not workflow:
                logger.warning(f"No workflow found for execution {execution.id}")
                return {}

            # Get destination settings from workflow
            destination_settings = {}
            if execution.pipeline_id:
                # ETL/Task pipeline execution - get settings from pipeline's workflow
                from pipeline_v2.models import Pipeline

                try:
                    pipeline = Pipeline.objects.get(id=execution.pipeline_id)
                    destination_settings = pipeline.workflow.destination_settings or {}
                    logger.debug(
                        f"Pipeline {execution.pipeline_id} destination settings: {bool(destination_settings)}"
                    )
                except Pipeline.DoesNotExist:
                    logger.warning(
                        f"Pipeline {execution.pipeline_id} not found for execution {execution.id}"
                    )
                    destination_settings = workflow.destination_settings or {}
            else:
                # API deployment or general workflow execution
                destination_settings = workflow.destination_settings or {}
                logger.debug(
                    f"Workflow {workflow.id} destination settings: {bool(destination_settings)}"
                )

            # Get connection type and connector instance from workflow endpoints
            from workflow_manager.endpoint_v2.models import WorkflowEndpoint

            connection_type = "FILESYSTEM"  # Default
            is_api = False
            connector_instance_data = None

            try:
                # Look for destination endpoint with connector instance
                dest_endpoint = (
                    WorkflowEndpoint.objects.select_related("connector_instance")
                    .filter(
                        workflow=workflow,
                        endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
                    )
                    .first()
                )

                if dest_endpoint:
                    connection_type = dest_endpoint.connection_type or "FILESYSTEM"
                    is_api = connection_type in ["API", "APPDEPLOYMENT"]

                    # Include connector instance details if available
                    if dest_endpoint.connector_instance:
                        connector_instance = dest_endpoint.connector_instance
                        connector_instance_data = {
                            "connector_id": connector_instance.connector_id,
                            "connector_settings": connector_instance.metadata or {},
                            "connector_name": getattr(
                                connector_instance, "connector_name", ""
                            ),
                        }
                        logger.debug(
                            f"Found connector instance: {connector_instance.connector_id}"
                        )

                    # Include endpoint configuration
                    if dest_endpoint.configuration:
                        destination_settings.update(dest_endpoint.configuration)

                    logger.debug(
                        f"Found destination endpoint: {connection_type}, is_api: {is_api}"
                    )
                else:
                    # Check if workflow has API deployments
                    if (
                        hasattr(workflow, "api_deployments")
                        and workflow.api_deployments.filter(is_active=True).exists()
                    ):
                        connection_type = "API"
                        is_api = True
                        logger.debug(
                            "Workflow has active API deployments, treating as API destination"
                        )

            except Exception as endpoint_error:
                logger.warning(
                    f"Failed to get endpoint info for workflow {workflow.id}: {str(endpoint_error)}"
                )

            # Get source connector information for file reading in manual review
            source_connector_data = None
            try:
                # Look for source endpoint with connector instance
                source_endpoint = (
                    WorkflowEndpoint.objects.select_related("connector_instance")
                    .filter(
                        workflow=workflow,
                        endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
                    )
                    .first()
                )

                if source_endpoint and source_endpoint.connector_instance:
                    source_connector_instance = source_endpoint.connector_instance
                    source_connector_data = {
                        "source_connector_id": source_connector_instance.connector_id,
                        "source_connector_settings": source_connector_instance.metadata
                        or {},
                    }
                    logger.debug(
                        f"Found source connector instance: {source_connector_instance.connector_id}"
                    )
                else:
                    logger.debug("No source connector instance found for workflow")

            except Exception as source_error:
                logger.warning(
                    f"Failed to get source connector info for workflow {workflow.id}: {str(source_error)}"
                )

            # Build comprehensive destination config
            destination_config = {
                "connection_type": connection_type,
                "settings": destination_settings,
                "is_api": is_api,
                "use_file_history": True,
            }

            # Add connector instance data if available
            if connector_instance_data:
                destination_config.update(connector_instance_data)
                logger.debug("Added connector instance data to destination config")
            else:
                logger.debug("No connector instance found for destination endpoint")

            # Add source connector data for manual review file reading
            if source_connector_data:
                destination_config.update(source_connector_data)
                logger.debug(
                    "Added source connector data to destination config for manual review"
                )

            return destination_config

        except Exception as e:
            logger.warning(
                f"Failed to get destination config for execution {execution.id}: {str(e)}"
            )
            return {}

    def _get_organization_context(self, execution: WorkflowExecution) -> dict:
        """Get organization context for execution."""
        try:
            # Get organization from the workflow, not directly from execution
            if execution.workflow and hasattr(execution.workflow, "organization"):
                org = execution.workflow.organization
                return {
                    "organization_id": str(org.id),
                    "organization_name": org.display_name,
                    "settings": {},  # Add organization-specific settings if needed
                }
            else:
                logger.warning(f"No organization found for execution {execution.id}")
                return {
                    "organization_id": None,
                    "organization_name": "Unknown",
                    "settings": {},
                }
        except Exception as e:
            logger.warning(
                f"Failed to get organization context for execution {execution.id}: {str(e)}"
            )
            return {
                "organization_id": None,
                "organization_name": "Unknown",
                "settings": {},
            }

    @action(detail=True, methods=["post"])
    def update_status(self, request, id=None):
        """Update workflow execution status."""
        try:
            logger.info(f"Updating status for execution {id}")
            execution = self.get_object()
            serializer = WorkflowExecutionStatusUpdateSerializer(data=request.data)

            if serializer.is_valid():
                validated_data = serializer.validated_data

                # FIXED: Use update_execution() method for proper wall-clock time calculation
                # This replaces manual field setting which bypassed execution time logic

                # Handle error message truncation before calling update_execution
                error_message = None
                if validated_data.get("error_message"):
                    error_msg = validated_data["error_message"]
                    if len(error_msg) > 256:
                        error_message = error_msg[:253] + "..."
                        logger.warning(
                            f"Error message truncated for execution {id} (original length: {len(error_msg)})"
                        )
                    else:
                        error_message = error_msg

                # Handle attempts increment
                increment_attempt = (
                    validated_data.get("attempts") is not None
                    and validated_data.get("attempts") > execution.attempts
                )

                # Use the model's update_execution method for proper wall-clock calculation
                from workflow_manager.workflow_v2.enums import ExecutionStatus

                status_enum = ExecutionStatus(validated_data["status"])
                execution.update_execution(
                    status=status_enum,
                    error=error_message,
                    increment_attempt=increment_attempt,
                )

                # Update total_files separately (not handled by update_execution)
                if validated_data.get("total_files") is not None:
                    execution.total_files = validated_data["total_files"]
                    execution.save()

                logger.info(
                    f"Updated workflow execution {id} status to {validated_data['status']}"
                )

                return Response(
                    {
                        "status": "updated",
                        "execution_id": str(execution.id),
                        "new_status": execution.status,
                    }
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Failed to update workflow execution status {id}: {str(e)}")
            return Response(
                {"error": "Failed to update workflow execution status", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileBatchCreateAPIView(APIView):
    """Internal API endpoint for creating file batches for workflow execution."""

    def post(self, request):
        """Create file execution records in batches."""
        try:
            serializer = FileBatchCreateSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            workflow_execution_id = validated_data["workflow_execution_id"]
            files = validated_data["files"]
            is_api = validated_data.get("is_api", False)

            # Get workflow execution
            workflow_execution = get_object_or_404(
                WorkflowExecution, id=workflow_execution_id
            )

            created_files = []
            skipped_files = []
            batch_id = uuid.uuid4()

            with transaction.atomic():
                for file_data in files:
                    try:
                        # Create file execution record
                        file_execution = WorkflowFileExecution.objects.create(
                            id=uuid.uuid4(),
                            workflow_execution=workflow_execution,
                            file_name=file_data.get("file_name", ""),
                            file_path=file_data.get("file_path", ""),
                            file_size=file_data.get("file_size", 0),
                            file_hash=file_data.get("file_hash", ""),
                            provider_file_uuid=file_data.get("provider_file_uuid", ""),
                            mime_type=file_data.get("mime_type", ""),
                            fs_metadata=file_data.get("fs_metadata", {}),
                            status="PENDING",
                        )

                        created_files.append(
                            {
                                "id": str(file_execution.id),
                                "file_name": file_execution.file_name,
                                "status": file_execution.status,
                            }
                        )

                    except Exception as file_error:
                        logger.warning(
                            f"Failed to create file execution for {file_data.get('file_name')}: {file_error}"
                        )
                        skipped_files.append(
                            {
                                "file_name": file_data.get("file_name", "unknown"),
                                "error": str(file_error),
                            }
                        )

            response_data = {
                "batch_id": batch_id,
                "workflow_execution_id": workflow_execution_id,
                "total_files": len(files),
                "created_file_executions": created_files,
                "skipped_files": skipped_files,
                "is_api": is_api,
            }

            response_serializer = FileBatchResponseSerializer(response_data)

            logger.info(
                f"Created file batch {batch_id} with {len(created_files)} files for execution {workflow_execution_id}"
            )

            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Failed to create file batch: {str(e)}")
            return Response(
                {"error": "Failed to create file batch", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ToolExecutionInternalAPIView(APIView):
    """Internal API endpoint for tool execution operations."""

    def get(self, request, workflow_id):
        """Get tool instances for a workflow."""
        try:
            # Get workflow with automatic organization filtering (via DefaultOrganizationManagerMixin)
            try:
                # This will automatically apply organization filtering via DefaultOrganizationManagerMixin
                workflow = Workflow.objects.get(id=workflow_id)
                logger.debug(f"Found workflow {workflow_id} for tool instances request")
            except Workflow.DoesNotExist:
                logger.error(f"Workflow {workflow_id} not found or not accessible")
                return Response(
                    {"error": "Workflow not found or access denied"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get tool instances for the workflow with organization filtering
            # Filter through the relationship: ToolInstance -> Workflow -> Organization
            tool_instances_queryset = ToolInstance.objects.filter(workflow=workflow)
            tool_instances_queryset = filter_queryset_by_organization(
                tool_instances_queryset, request, "workflow__organization"
            )
            tool_instances = tool_instances_queryset.order_by("step")

            instances_data = []
            for tool_instance in tool_instances:
                instances_data.append(
                    {
                        "id": str(tool_instance.id),
                        "tool_id": str(tool_instance.tool_id)
                        if tool_instance.tool_id
                        else None,
                        "step": tool_instance.step,
                        "tool_settings": tool_instance.metadata or {},
                        "created_at": tool_instance.created_at.isoformat()
                        if tool_instance.created_at
                        else None,
                        "modified_at": tool_instance.modified_at.isoformat()
                        if tool_instance.modified_at
                        else None,
                    }
                )

            response_data = {
                "workflow_id": workflow_id,
                "tool_instances": instances_data,
                "total_instances": len(instances_data),
            }

            logger.info(
                f"Retrieved {len(instances_data)} tool instances for workflow {workflow_id}"
            )
            return Response(response_data)

        except Exception as e:
            logger.error(
                f"Failed to get tool instances for workflow {workflow_id}: {str(e)}"
            )
            return Response(
                {"error": "Failed to get tool instances", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ExecutionFinalizationAPIView class removed - it was unused dead code
# Workers now use simple update_workflow_execution_status instead of complex finalization
# This eliminates unnecessary API complexity and improves callback performance


class WorkflowFileExecutionCheckActiveAPIView(APIView):
    """Internal API for checking if files are actively being processed."""

    def post(self, request):
        """Check if files are in PENDING or EXECUTING state in other workflow executions."""
        try:
            workflow_id = request.data.get("workflow_id")
            # Support both legacy and new formats
            provider_file_uuids = request.data.get(
                "provider_file_uuids", []
            )  # Legacy format
            files = request.data.get("files", [])  # New format: [{uuid, path}]
            current_execution_id = request.data.get("current_execution_id")

            # Convert legacy format to new format for backward compatibility
            if provider_file_uuids and not files:
                files = [{"uuid": uuid, "path": None} for uuid in provider_file_uuids]
            elif files:
                # Ensure files have required fields
                for file_data in files:
                    if "uuid" not in file_data:
                        return Response(
                            {"error": "Each file must have 'uuid' field"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            if not workflow_id or not files:
                return Response(
                    {
                        "error": "workflow_id and files (or provider_file_uuids) are required"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            logger.info(
                f"Checking active files for workflow {workflow_id}, "
                f"excluding execution {current_execution_id}, "
                f"checking {len(files)} files"
            )

            # Check for files in PENDING or EXECUTING state in other workflow executions
            active_files = {}  # {uuid: [execution_data]} - legacy format
            active_identifiers = set()  # Composite identifiers for new format
            db_queries = 0

            # Prepare all files for database check
            # Note: Workers already check cache before calling this API, so no need to check again
            files_needing_db_check = []

            for file_data in files:
                provider_uuid = file_data["uuid"]
                file_path = file_data.get("path")
                composite_id = (
                    f"{provider_uuid}:{file_path}" if file_path else provider_uuid
                )

                # All files need database check
                files_needing_db_check.append(
                    {
                        "uuid": provider_uuid,
                        "path": file_path,
                        "composite_id": composite_id,
                    }
                )

            # Bulk database query for all files
            if files_needing_db_check:
                logger.info(
                    f"[ActiveCheck] Performing bulk database check for {len(files_needing_db_check)} files"
                )
                self._bulk_database_check(
                    files_needing_db_check=files_needing_db_check,
                    workflow_id=workflow_id,
                    current_execution_id=current_execution_id,
                    active_files=active_files,
                    active_identifiers=active_identifiers,
                )
                db_queries = 2  # At most 2 bulk queries (path-aware + legacy)

            logger.info(
                f"[ActiveCheck] Active check complete: {len(active_files)}/{len(files)} files active "
                f"(db_queries: {db_queries})"
            )

            # Log final active identifiers for debugging
            if active_identifiers:
                logger.debug(
                    f"[ActiveCheck] Active identifiers: {sorted(active_identifiers)}"
                )
            else:
                logger.debug("[ActiveCheck] No files are currently active")

            return Response(
                {
                    "active_files": active_files,  # Legacy format: {uuid: [execution_data]}
                    "active_uuids": list(
                        active_files.keys()
                    ),  # Legacy format: [uuid1, uuid2]
                    "active_identifiers": list(
                        active_identifiers
                    ),  # New format: ["uuid:path", "uuid2:path2"]
                    "total_checked": len(files),
                    "total_active": len(active_files),
                    "cache_stats": {
                        "db_queries": db_queries,
                    },
                }
            )

        except Exception as e:
            logger.error(f"Error checking active files: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to check active files", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _bulk_database_check(
        self,
        files_needing_db_check: list[dict],
        workflow_id: str,
        current_execution_id: str | None,
        active_files: dict,
        active_identifiers: set,
    ):
        """Perform bulk database queries instead of individual queries for each file."""
        if not files_needing_db_check:
            return

        # Separate files by query type
        path_aware_files = [f for f in files_needing_db_check if f["path"] is not None]
        legacy_files = [f for f in files_needing_db_check if f["path"] is None]

        logger.debug(
            f"[ActiveCheck] Querying {len(path_aware_files)} path-aware, "
            f"{len(legacy_files)} UUID-only files"
        )

        # Query 1: Bulk query for path-aware files
        if path_aware_files:
            self._bulk_query_path_aware(
                path_aware_files,
                workflow_id,
                current_execution_id,
                active_files,
                active_identifiers,
            )

        # Query 2: Bulk query for UUID-only files
        if legacy_files:
            self._bulk_query_uuid_only(
                legacy_files,
                workflow_id,
                current_execution_id,
                active_files,
                active_identifiers,
            )

    def _bulk_query_path_aware(
        self,
        path_aware_files: list[dict],
        workflow_id: str,
        current_execution_id: str | None,
        active_files: dict,
        active_identifiers: set,
    ):
        """Bulk query for files with specific paths using two-step workflow scoping."""
        from django.db.models import Q

        # Step 1: Get ACTIVE workflow executions for this workflow
        active_workflow_executions = WorkflowExecution.objects.filter(
            workflow_id=workflow_id, status__in=["PENDING", "EXECUTING"]
        )

        if current_execution_id:
            active_workflow_executions = active_workflow_executions.exclude(
                id=current_execution_id
            )

        active_execution_ids = list(
            active_workflow_executions.values_list("id", flat=True)
        )

        if not active_execution_ids:
            logger.debug(
                "[ActiveCheck] No active workflow executions found, path-aware query returns 0 results"
            )
            return

        # Step 2: Build OR conditions for file matching: (uuid1 AND path1) OR (uuid2 AND path2) OR ...
        path_conditions = Q()
        for file_info in path_aware_files:
            path_conditions |= Q(
                provider_file_uuid=file_info["uuid"], file_path=file_info["path"]
            )

        # Step 3: Execute bulk query on workflow_file_executions from active workflow executions only
        query = WorkflowFileExecution.objects.filter(
            workflow_execution_id__in=active_execution_ids,  # Scoped to active workflow executions
            status__in=["PENDING", "EXECUTING"],  # File execution must also be active
        ).filter(path_conditions)

        active_executions = query.values(
            "id",
            "workflow_execution_id",
            "file_name",
            "file_path",
            "status",
            "created_at",
            "provider_file_uuid",
        )

        logger.info(
            f"[ActiveCheck] Path-aware query found {active_executions.count()} active records"
        )

        # Map results back to files with validation
        for record in active_executions:
            provider_uuid = record["provider_file_uuid"]
            file_path = record["file_path"]
            composite_id = f"{provider_uuid}:{file_path}"
            execution_id = record["workflow_execution_id"]

            # Validation: Ensure this execution ID is in our expected active executions list
            if execution_id not in active_execution_ids:
                logger.error(
                    f"[ActiveCheck] VALIDATION ERROR: Found file execution {record['id']} "
                    f"with workflow_execution_id {execution_id} that's not in our active executions list!"
                )
                continue

            logger.debug(
                f"[ActiveCheck]   Active record {record['id']}: "
                f"uuid={provider_uuid[:8]}..., status={record['status']}, "
                f"path={file_path}, workflow_execution={execution_id} ✓"
            )

            # Track in both formats
            if provider_uuid not in active_files:
                active_files[provider_uuid] = []
            active_files[provider_uuid].append(dict(record))
            active_identifiers.add(composite_id)

            logger.debug(f"[ActiveCheck] File {composite_id} is actively being processed")

    def _bulk_query_uuid_only(
        self,
        legacy_files: list[dict],
        workflow_id: str,
        current_execution_id: str | None,
        active_files: dict,
        active_identifiers: set,
    ):
        """Bulk query for UUID-only files (no path available) using two-step workflow scoping."""
        # Step 1: Get ACTIVE workflow executions for this workflow
        active_workflow_executions = WorkflowExecution.objects.filter(
            workflow_id=workflow_id, status__in=["PENDING", "EXECUTING"]
        )

        if current_execution_id:
            active_workflow_executions = active_workflow_executions.exclude(
                id=current_execution_id
            )

        active_execution_ids = list(
            active_workflow_executions.values_list("id", flat=True)
        )

        if not active_execution_ids:
            logger.debug(
                "[ActiveCheck] No active workflow executions found, UUID-only query returns 0 results"
            )
            return

        # Step 2: Extract UUIDs for IN query
        uuid_only_uuids = [f["uuid"] for f in legacy_files]

        # Step 3: Execute bulk query on workflow_file_executions from active workflow executions only
        query = WorkflowFileExecution.objects.filter(
            workflow_execution_id__in=active_execution_ids,  # Scoped to active workflow executions
            provider_file_uuid__in=uuid_only_uuids,
            status__in=["PENDING", "EXECUTING"],  # File execution must also be active
        )

        logger.debug(f"[ActiveCheck] Legacy bulk SQL: {query.query}")

        active_executions = query.values(
            "id",
            "workflow_execution_id",
            "file_name",
            "file_path",
            "status",
            "created_at",
            "provider_file_uuid",
        )

        logger.info(
            f"[ActiveCheck] UUID-only query found {active_executions.count()} active records"
        )

        # Map results back to files with validation
        for record in active_executions:
            provider_uuid = record["provider_file_uuid"]
            composite_id = provider_uuid  # Legacy: no path suffix
            execution_id = record["workflow_execution_id"]

            # Validation: Ensure this execution ID is in our expected active executions list
            if execution_id not in active_execution_ids:
                logger.error(
                    f"[ActiveCheck] VALIDATION ERROR: Found file execution {record['id']} "
                    f"with workflow_execution_id {execution_id} that's not in our active executions list!"
                )
                continue

            logger.debug(
                f"[ActiveCheck]   Active record {record['id']}: "
                f"uuid={provider_uuid[:8]}..., status={record['status']}, "
                f"path={record['file_path']}, workflow_execution={execution_id} ✓"
            )

            # Track in both formats
            if provider_uuid not in active_files:
                active_files[provider_uuid] = []
            active_files[provider_uuid].append(dict(record))
            active_identifiers.add(composite_id)

            logger.info(
                f"[ActiveCheck] File {composite_id} is actively being processed (legacy)"
            )


class WorkflowFileExecutionAPIView(APIView):
    """Internal API for workflow file execution operations."""

    def post(self, request):
        """Get or create workflow file execution record."""
        try:
            execution_id = request.data.get("execution_id")
            file_hash = request.data.get("file_hash", {})
            workflow_id = request.data.get("workflow_id")

            logger.info(
                f"1Received file execution request for execution {execution_id} and workflow {workflow_id}"
            )

            if not execution_id or not workflow_id:
                return Response(
                    {"error": "execution_id and workflow_id are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            logger.info(
                f"2Received file execution request for execution {execution_id} and workflow {workflow_id}"
            )
            # Get workflow execution
            try:
                workflow_execution = WorkflowExecution.objects.get(id=execution_id)
            except WorkflowExecution.DoesNotExist:
                return Response(
                    {"error": f"Workflow execution {execution_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            logger.info(
                f"3Received file execution request for execution {execution_id} and workflow {workflow_id}"
            )
            # Get or create workflow file execution
            file_execution, created = WorkflowFileExecution.objects.get_or_create(
                workflow_execution=workflow_execution,
                file_hash=file_hash.get("file_hash", ""),
                defaults={
                    "file_name": file_hash.get("file_name", ""),
                    "file_path": file_hash.get("file_path", ""),
                    "file_size": file_hash.get("file_size", 0),
                    "mime_type": file_hash.get("mime_type", ""),
                    "provider_file_uuid": file_hash.get("provider_file_uuid"),
                    "fs_metadata": file_hash.get("fs_metadata", {}),
                    "status": "PENDING",
                },
            )

            logger.info(f"4Received file execution request for file_hash {file_hash}")
            return Response(
                {
                    "id": str(file_execution.id),
                    "file_name": file_execution.file_name,
                    "file_path": file_execution.file_path,
                    "status": file_execution.status,
                    "created": created,
                }
            )

        except Exception as e:
            logger.error(f"Failed to get/create workflow file execution: {str(e)}")
            return Response(
                {
                    "error": "Failed to get/create workflow file execution",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkflowExecuteFileAPIView(APIView):
    """Internal API for executing workflow for a single file."""

    def post(self, request):
        """Execute workflow for a single file."""
        try:
            workflow_id = request.data.get("workflow_id")
            execution_id = request.data.get("execution_id")
            file_data = request.data.get("file_data", {})
            organization_id = request.data.get("organization_id")

            if not all([workflow_id, execution_id, file_data, organization_id]):
                return Response(
                    {
                        "error": "workflow_id, execution_id, file_data, and organization_id are required"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Set organization context
            StateStore.set(Account.ORGANIZATION_ID, organization_id)

            # Get workflow and execution
            try:
                workflow = Workflow.objects.get(id=workflow_id)
                workflow_execution = WorkflowExecution.objects.get(id=execution_id)
            except (Workflow.DoesNotExist, WorkflowExecution.DoesNotExist) as e:
                return Response(
                    {"error": f"Workflow or execution not found: {str(e)}"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get tool instances
            tool_instances = ToolInstance.objects.filter(workflow=workflow).order_by(
                "step"
            )

            # Execute workflow using WorkflowExecutionServiceHelper
            try:
                from workflow_manager.workflow_v2.execution import (
                    WorkflowExecutionServiceHelper,
                )

                execution_helper = WorkflowExecutionServiceHelper(
                    workflow=workflow,
                    tool_instances=list(tool_instances),
                    organization_id=organization_id,
                    workflow_execution=workflow_execution,
                )

                # Execute the workflow for this file
                result = execution_helper.execute_single_file(
                    file_data=file_data,
                    file_name=file_data.get("name", ""),
                    file_path=file_data.get("file_path", ""),
                )

                return Response(
                    {
                        "status": "success",
                        "execution_id": execution_id,
                        "result": result,
                        "file_name": file_data.get("name"),
                    }
                )

            except Exception as exec_error:
                logger.error(f"Workflow execution failed: {str(exec_error)}")
                return Response(
                    {
                        "status": "error",
                        "execution_id": execution_id,
                        "error": str(exec_error),
                        "file_name": file_data.get("name"),
                    }
                )

        except Exception as e:
            logger.error(f"Failed to execute workflow for file: {str(e)}")
            return Response(
                {"error": "Failed to execute workflow for file", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkflowEndpointAPIView(APIView):
    """Internal API for getting workflow endpoints.
    Used by workers to determine if a workflow is API-based or filesystem-based.
    """

    def get(self, request, workflow_id):
        """Get workflow endpoints for connection type detection."""
        try:
            from utils.user_context import UserContext

            from workflow_manager.endpoint_v2.models import WorkflowEndpoint

            # Enhanced debug logging for organization context
            organization_id = getattr(request, "organization_id", None)
            organization_from_context = UserContext.get_organization()
            statestore_org_id = StateStore.get(Account.ORGANIZATION_ID)

            request_debug = {
                "workflow_id": str(workflow_id),
                "request_organization_id": organization_id,
                "statestore_org_id": statestore_org_id,
                "usercontext_organization": str(organization_from_context.id)
                if organization_from_context
                else None,
                "usercontext_org_name": organization_from_context.display_name
                if organization_from_context
                else None,
                "headers": dict(request.headers),
                "internal_service": getattr(request, "internal_service", False),
                "authenticated_via": getattr(request, "authenticated_via", None),
                "path": request.path,
            }
            logger.info(f"WorkflowEndpointAPIView debug - {request_debug}")

            # Get workflow using the DefaultOrganizationManagerMixin which automatically filters by organization
            try:
                # This will automatically apply organization filtering via DefaultOrganizationManagerMixin
                workflow = Workflow.objects.get(id=workflow_id)

                logger.info(
                    f"Found workflow {workflow_id}: organization={workflow.organization_id}, name={getattr(workflow, 'workflow_name', 'Unknown')}"
                )

            except Workflow.DoesNotExist:
                logger.error(
                    f"Workflow {workflow_id} not found or not accessible by organization {organization_id}"
                )
                return Response(
                    {"error": "Workflow not found or access denied"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get workflow endpoints with connector instance data
            workflow_endpoints = WorkflowEndpoint.objects.select_related(
                "connector_instance"
            ).filter(workflow=workflow)

            source_endpoint = None
            destination_endpoint = None

            has_api_endpoints = False

            for endpoint in workflow_endpoints:
                endpoint_data = WorkflowEndpointConfigData(
                    endpoint_id=endpoint.id,
                    endpoint_type=endpoint.endpoint_type,
                    connection_type=endpoint.connection_type,
                    configuration=endpoint.configuration,
                )

                # Include connector instance information if available
                if endpoint.connector_instance:
                    connector_instance_data = ConnectorInstanceData(
                        connector_id=endpoint.connector_instance.connector_id,
                        connector_name=endpoint.connector_instance.connector_name,
                        connector_metadata=endpoint.connector_instance.metadata or {},
                    )
                    endpoint_data.connector_instance = connector_instance_data
                    # endpoint_data["connector_instance"] = connector_instance_data
                    logger.debug(
                        f"Added connector instance data for endpoint {endpoint.id}: {endpoint.connector_instance.connector_id}"
                    )
                else:
                    endpoint_data.connector_instance = None
                    # endpoint_data["connector_instance"] = None
                    logger.debug(
                        f"No connector instance found for endpoint {endpoint.id}"
                    )

                if endpoint.endpoint_type == WorkflowEndpoint.EndpointType.SOURCE:
                    source_endpoint = endpoint_data
                elif endpoint.endpoint_type == WorkflowEndpoint.EndpointType.DESTINATION:
                    destination_endpoint = endpoint_data
                    if endpoint.connection_type == ConnectionType.API.value:
                        has_api_endpoints = True

            endpoint_config = WorkflowEndpointConfigResponseData(
                workflow_id=str(workflow_id),
                has_api_endpoints=has_api_endpoints,
                source_endpoint=source_endpoint,
                destination_endpoint=destination_endpoint,
            )

            response_data = endpoint_config.to_dict()

            logger.info(
                f"Retrieved endpoints for workflow {workflow_id}, API endpoints: {has_api_endpoints}"
            )
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Failed to get workflow endpoints for {workflow_id}: {str(e)}")
            return Response(
                {"error": "Failed to get workflow endpoints", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkflowSourceFilesAPIView(APIView):
    """Internal API for getting workflow source files.
    Used by workers to get source files for processing.
    """

    def post(self, request, workflow_id):
        """Get source files for a workflow execution."""
        try:
            from utils.user_context import UserContext

            from unstract.workflow_execution.enums import LogStage
            from workflow_manager.endpoint_v2.source import SourceConnector
            from workflow_manager.utils.workflow_log import WorkflowLog

            # Get request data
            execution_id = request.data.get("execution_id")
            pipeline_id = request.data.get("pipeline_id")
            use_file_history = request.data.get("use_file_history", True)

            if not execution_id:
                return Response(
                    {"error": "execution_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Enhanced debug logging for organization context
            organization_id = getattr(request, "organization_id", None)
            organization_from_context = UserContext.get_organization()
            statestore_org_id = StateStore.get(Account.ORGANIZATION_ID)

            request_debug = {
                "workflow_id": str(workflow_id),
                "execution_id": str(execution_id),
                "pipeline_id": str(pipeline_id) if pipeline_id else None,
                "request_organization_id": organization_id,
                "statestore_org_id": statestore_org_id,
                "usercontext_organization": str(organization_from_context.id)
                if organization_from_context
                else None,
                "use_file_history": use_file_history,
            }
            logger.info(f"WorkflowSourceFilesAPIView debug - {request_debug}")

            # Get workflow using the DefaultOrganizationManagerMixin which automatically filters by organization
            try:
                workflow = Workflow.objects.get(id=workflow_id)
                logger.info(f"Found workflow {workflow_id} for source files request")
            except Workflow.DoesNotExist:
                logger.error(f"Workflow {workflow_id} not found or not accessible")
                return Response(
                    {"error": "Workflow not found or access denied"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get workflow execution
            try:
                WorkflowExecution.objects.get(id=execution_id)
                logger.info(f"Found workflow execution {execution_id}")
            except WorkflowExecution.DoesNotExist:
                logger.error(f"Workflow execution {execution_id} not found")
                return Response(
                    {"error": "Workflow execution not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Create workflow log
            workflow_log = WorkflowLog(
                execution_id=execution_id,
                organization_id=organization_id,
                log_stage=LogStage.INITIALIZE,
                pipeline_id=pipeline_id,
            )

            # Create source connector
            source = SourceConnector(
                workflow=workflow,
                execution_id=str(execution_id),
                workflow_log=workflow_log,
                use_file_history=use_file_history,
                organization_id=organization_id,
            )

            # Validate and get source files
            source.validate()

            # Get input files from source (this includes file listing and processing)
            input_files, total_files = source.list_files_from_source({})

            # Convert input_files to serializable format and include connector context
            serializable_files = {}
            connector_metadata = None
            connector_id = None

            # Get connector metadata from the workflow endpoint for FILESYSTEM access
            if source.endpoint and source.endpoint.connector_instance:
                connector_metadata = source.endpoint.connector_instance.connector_metadata
                connector_id = source.endpoint.connector_instance.connector_id
                logger.info(f"Including connector context: connector_id={connector_id}")

            for file_name, file_hash in input_files.items():
                if hasattr(file_hash, "to_json"):
                    file_data = file_hash.to_json()
                else:
                    file_data = file_hash

                # Add connector context to each file for worker access
                if connector_metadata and connector_id:
                    file_data["connector_metadata"] = connector_metadata
                    file_data["connector_id"] = connector_id

                serializable_files[file_name] = file_data

            logger.info(
                f"Retrieved {total_files} source files for workflow {workflow_id}, execution {execution_id}"
            )

            return Response(
                {
                    "files": serializable_files,
                    "total_files": total_files,
                    "workflow_id": str(workflow_id),
                    "execution_id": str(execution_id),
                    "pipeline_id": str(pipeline_id) if pipeline_id else None,
                }
            )

        except Exception as e:
            logger.error(
                f"Failed to get source files for workflow {workflow_id}: {str(e)}",
                exc_info=True,
            )
            return Response(
                {"error": "Failed to get source files", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileCountIncrementAPIView(APIView):
    """Internal API for incrementing file counts during execution.
    Replicates Django ExecutionCacheUtils functionality for workers.
    """

    def post(self, request):
        """Increment file counts for execution."""
        try:
            workflow_id = request.data.get("workflow_id")
            execution_id = request.data.get("execution_id")
            increment_type = request.data.get("increment_type")  # 'completed' or 'failed'

            if not all([workflow_id, execution_id, increment_type]):
                return Response(
                    {
                        "error": "workflow_id, execution_id, and increment_type are required"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get workflow execution
            try:
                WorkflowExecution.objects.get(id=execution_id)
            except WorkflowExecution.DoesNotExist:
                return Response(
                    {"error": "Workflow execution not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Use Django backend's ExecutionCacheUtils to increment counts
            from workflow_manager.execution.execution_cache_utils import (
                ExecutionCacheUtils,
            )

            if increment_type == "completed":
                ExecutionCacheUtils.increment_completed_files(
                    workflow_id=workflow_id, execution_id=execution_id
                )
                logger.info(f"Incremented completed files for execution {execution_id}")
            elif increment_type == "failed":
                ExecutionCacheUtils.increment_failed_files(
                    workflow_id=workflow_id, execution_id=execution_id
                )
                logger.info(f"Incremented failed files for execution {execution_id}")
            else:
                return Response(
                    {
                        "error": f"Invalid increment_type: {increment_type}. Must be 'completed' or 'failed'"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {
                    "success": True,
                    "workflow_id": workflow_id,
                    "execution_id": execution_id,
                    "increment_type": increment_type,
                }
            )

        except Exception as e:
            logger.error(f"Failed to increment file count: {str(e)}")
            return Response(
                {"error": "Failed to increment file count", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PipelineStatusUpdateAPIView(APIView):
    """Internal API for updating pipeline status.
    Used by workers to update pipeline execution status.
    """

    def post(self, request, pipeline_id):
        """Update pipeline status."""
        try:
            from pipeline_v2.models import Pipeline

            from workflow_manager.utils.pipeline_utils import PipelineUtils

            # Get request data
            execution_id = request.data.get("execution_id")
            status_value = request.data.get("status")

            if not execution_id or not status_value:
                return Response(
                    {"error": "execution_id and status are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get pipeline with organization filtering
            try:
                # Apply organization filtering to pipeline query
                pipeline_queryset = Pipeline.objects.filter(id=pipeline_id)
                pipeline_queryset = filter_queryset_by_organization(
                    pipeline_queryset, request, "organization"
                )
                pipeline_queryset.get()
                logger.info(
                    f"Found pipeline {pipeline_id} for status update (org: {getattr(request, 'organization_id', 'unknown')})"
                )
            except Pipeline.DoesNotExist:
                org_id = getattr(request, "organization_id", "unknown")
                logger.error(
                    f"Pipeline {pipeline_id} not found or not accessible by organization {org_id}"
                )
                return Response(
                    {"error": "Pipeline not found"}, status=status.HTTP_404_NOT_FOUND
                )

            # Get workflow execution with organization filtering
            try:
                # Apply organization filtering to workflow execution query
                execution_queryset = WorkflowExecution.objects.filter(id=execution_id)
                execution_queryset = filter_queryset_by_organization(
                    execution_queryset, request, "workflow__organization"
                )
                workflow_execution = execution_queryset.get()
                logger.info(
                    f"Found workflow execution {execution_id} (org: {getattr(request, 'organization_id', 'unknown')})"
                )
            except WorkflowExecution.DoesNotExist:
                org_id = getattr(request, "organization_id", "unknown")
                logger.error(
                    f"Workflow execution {execution_id} not found or not accessible by organization {org_id}"
                )
                return Response(
                    {"error": "Workflow execution not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Update pipeline status using the utility method
            PipelineUtils.update_pipeline_status(
                pipeline_id=str(pipeline_id), workflow_execution=workflow_execution
            )

            logger.info(
                f"Updated pipeline {pipeline_id} status for execution {execution_id}"
            )

            return Response(
                {
                    "status": "updated",
                    "pipeline_id": str(pipeline_id),
                    "execution_id": str(execution_id),
                    "new_status": status_value,
                }
            )

        except Exception as e:
            logger.error(
                f"Failed to update pipeline {pipeline_id} status: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to update pipeline status", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkflowDefinitionAPIView(APIView):
    """Internal API endpoint for getting workflow definitions.
    Fixed to handle missing endpoints gracefully and use correct workflow type detection.
    """

    def get(self, request, workflow_id):
        """Get workflow definition with proper type detection and endpoint handling."""
        try:
            from workflow_manager.workflow_v2.models.workflow import Workflow

            # Get workflow with organization filtering
            try:
                workflow = Workflow.objects.get(id=workflow_id)
                # Verify organization access
                filter_queryset_by_organization(
                    Workflow.objects.filter(id=workflow_id), request, "organization"
                ).get()
            except Workflow.DoesNotExist:
                return Response(
                    {"error": "Workflow not found or access denied"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Step 1: Get source configuration with graceful error handling
            source_config = self._get_source_endpoint_config(workflow_id, workflow)

            # Step 2: Get destination configuration with graceful error handling
            destination_config = self._get_destination_endpoint_config(
                workflow_id, workflow
            )

            # Step 3: Build comprehensive workflow definition using dataclasses
            workflow_definition = WorkflowDefinitionResponseData(
                workflow_id=str(workflow.id),
                workflow_name=workflow.workflow_name,
                source_config=source_config,
                destination_config=destination_config,
                organization_id=str(workflow.organization.organization_id),
                created_at=workflow.created_at.isoformat(),
                modified_at=workflow.modified_at.isoformat(),
                is_active=workflow.is_active,
            )

            response_data = workflow_definition.to_dict()

            logger.info(
                f"Retrieved workflow definition for {workflow_id}: {workflow_definition.workflow_type} (source: {workflow_definition.source_config.connection_type})"
            )
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(
                f"Failed to get workflow definition for {workflow_id}: {str(e)}",
                exc_info=True,
            )
            return Response(
                {"error": "Failed to get workflow definition", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_source_endpoint_config(
        self, workflow_id: str, workflow
    ) -> WorkflowEndpointConfigData:
        """Get source endpoint configuration with credential resolution."""
        try:
            source_endpoint = WorkflowEndpointUtils.get_endpoint_for_workflow_by_type(
                workflow_id, WorkflowEndpoint.EndpointType.SOURCE
            )

            # Start with folder/path configuration from endpoint
            merged_configuration = source_endpoint.configuration or {}

            # Create connector instance data and resolve credentials if available
            connector_instance_data = None
            if source_endpoint.connector_instance:
                connector_instance = source_endpoint.connector_instance

                # Use exact same pattern as backend source.py
                # Get connector metadata (which contains decrypted credentials)
                connector_credentials = {}
                try:
                    # Follow backend pattern: use connector.metadata for credentials
                    # This contains the actual decrypted credentials (json_credentials, project_id, etc.)
                    connector_credentials = connector_instance.metadata or {}

                    # Optionally refresh OAuth tokens if needed (like backend does)
                    if connector_instance.connector_auth:
                        try:
                            # This refreshes tokens and updates metadata if needed
                            connector_instance.get_connector_metadata()
                            # Use the updated metadata
                            connector_credentials = connector_instance.metadata or {}
                            logger.debug(
                                f"Refreshed connector metadata for {connector_instance.connector_id}"
                            )
                        except Exception as refresh_error:
                            logger.warning(
                                f"Failed to refresh connector metadata for {connector_instance.id}: {str(refresh_error)}"
                            )
                            # Continue with existing metadata

                    logger.debug(
                        f"Retrieved connector settings for {connector_instance.connector_id}"
                    )

                except Exception as cred_error:
                    logger.warning(
                        f"Failed to retrieve connector settings for {connector_instance.id}: {str(cred_error)}"
                    )
                    # Continue without credentials - let connector handle the error

                # Merge folder configuration with connector credentials
                # Folder settings take precedence over connector defaults
                merged_configuration = {**connector_credentials, **merged_configuration}

                connector_instance_data = ConnectorInstanceData(
                    connector_id=connector_instance.connector_id,
                    connector_name=getattr(connector_instance, "connector_name", ""),
                    connector_metadata=connector_instance.metadata or {},
                )

            logger.debug(
                f"Found source endpoint for workflow {workflow_id}: {source_endpoint.connection_type} with {len(merged_configuration)} config keys"
            )
            return WorkflowEndpointConfigData(
                endpoint_id=str(source_endpoint.id),
                endpoint_type=source_endpoint.endpoint_type,
                connection_type=source_endpoint.connection_type,
                configuration=merged_configuration,
                connector_instance=connector_instance_data,
            )

        except WorkflowEndpoint.DoesNotExist:
            logger.info(
                f"No source endpoint found for workflow {workflow_id}, returning empty config"
            )
            return WorkflowEndpointConfigData(
                endpoint_id="",
                endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
                connection_type="NONE",
            )
        except Exception as e:
            logger.warning(
                f"Error getting source endpoint for workflow {workflow_id}: {str(e)}"
            )
            return WorkflowEndpointConfigData(
                endpoint_id="",
                endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
                connection_type="NONE",
            )

    def _get_destination_endpoint_config(
        self, workflow_id: str, workflow
    ) -> WorkflowEndpointConfigData:
        """Get destination endpoint configuration with credential resolution."""
        try:
            destination_endpoint = (
                WorkflowEndpointUtils.get_endpoint_for_workflow_by_type(
                    workflow_id, WorkflowEndpoint.EndpointType.DESTINATION
                )
            )

            # Start with configuration from endpoint
            merged_configuration = destination_endpoint.configuration or {}

            # Create connector instance data and resolve credentials if available
            connector_instance_data = None
            if destination_endpoint.connector_instance:
                connector_instance = destination_endpoint.connector_instance

                # Use exact same pattern as backend source.py
                # Get connector metadata (which contains decrypted credentials)
                connector_credentials = {}
                try:
                    # Follow backend pattern: use connector.metadata for credentials
                    # This contains the actual decrypted credentials (host, database, username, password, etc.)
                    connector_credentials = connector_instance.metadata or {}

                    # Optionally refresh OAuth tokens if needed (like backend does)
                    if connector_instance.connector_auth:
                        try:
                            # This refreshes tokens and updates metadata if needed
                            connector_instance.get_connector_metadata()
                            # Use the updated metadata
                            connector_credentials = connector_instance.metadata or {}
                            logger.debug(
                                f"Refreshed destination connector metadata for {connector_instance.connector_id}"
                            )
                        except Exception as refresh_error:
                            logger.warning(
                                f"Failed to refresh destination connector metadata for {connector_instance.id}: {str(refresh_error)}"
                            )
                            # Continue with existing metadata

                    logger.debug(
                        f"Retrieved destination connector settings for {connector_instance.connector_id}"
                    )

                except Exception as cred_error:
                    logger.warning(
                        f"Failed to retrieve destination connector settings for {connector_instance.id}: {str(cred_error)}"
                    )
                    # Continue without credentials - let connector handle the error

                # Merge configuration with connector credentials
                # Endpoint settings take precedence over connector defaults
                merged_configuration = {**connector_credentials, **merged_configuration}

                connector_instance_data = ConnectorInstanceData(
                    connector_id=connector_instance.connector_id,
                    connector_name=connector_instance.connector_name,
                    connector_metadata=connector_instance.metadata or {},
                )

            logger.debug(
                f"Found destination endpoint for workflow {workflow_id}: {destination_endpoint.connection_type} with {len(merged_configuration)} config keys"
            )
            return WorkflowEndpointConfigData(
                endpoint_id=str(destination_endpoint.id),
                endpoint_type=destination_endpoint.endpoint_type,
                connection_type=destination_endpoint.connection_type,
                configuration=merged_configuration,
                connector_instance=connector_instance_data,
            )

        except WorkflowEndpoint.DoesNotExist:
            logger.info(
                f"No destination endpoint found for workflow {workflow_id}, returning empty config"
            )
            return WorkflowEndpointConfigData(
                endpoint_id="",
                endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
                connection_type="NONE",
            )
        except Exception as e:
            logger.warning(
                f"Error getting destination endpoint for workflow {workflow_id}: {str(e)}"
            )
            return WorkflowEndpointConfigData(
                endpoint_id="",
                endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
                connection_type="NONE",
            )


class PipelineTypeAPIView(APIView):
    """Internal API endpoint for determining pipeline type.

    Checks APIDeployment first, then Pipeline model to determine if pipeline is:
    - API (if found in APIDeployment model)
    - ETL/TASK/APP (if found in Pipeline model with pipeline_type field)
    """

    def get(self, request, pipeline_id):
        """Determine pipeline type from APIDeployment or Pipeline models."""
        try:
            from api_v2.models import APIDeployment
            from pipeline_v2.models import Pipeline

            organization_id = getattr(request, "organization_id", None)

            # First check if this is an API deployment
            try:
                api_deployment = APIDeployment.objects.get(id=pipeline_id)
                # Verify organization access
                if (
                    organization_id
                    and str(api_deployment.organization.organization_id)
                    != organization_id
                ):
                    return Response(
                        {"error": "API deployment not found in organization"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                logger.info(f"Pipeline {pipeline_id} identified as API deployment")
                return Response(
                    {
                        "pipeline_id": str(pipeline_id),
                        "pipeline_type": "API",
                        "source": "api_deployment",
                        "workflow_id": str(api_deployment.workflow_id),
                        "display_name": api_deployment.display_name,
                        "is_active": api_deployment.is_active,
                    },
                    status=status.HTTP_200_OK,
                )

            except APIDeployment.DoesNotExist:
                # Not an API deployment, check Pipeline model
                pass

            # Check if this is a regular pipeline (ETL/TASK/APP)
            try:
                pipeline = Pipeline.objects.get(id=pipeline_id)
                # Verify organization access
                if (
                    organization_id
                    and str(pipeline.organization.organization_id) != organization_id
                ):
                    return Response(
                        {"error": "Pipeline not found in organization"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Map Pipeline.PipelineType to expected values
                pipeline_type = pipeline.pipeline_type
                if pipeline_type == Pipeline.PipelineType.ETL:
                    resolved_type = "ETL"
                elif pipeline_type == Pipeline.PipelineType.TASK:
                    resolved_type = "TASK"
                elif pipeline_type == Pipeline.PipelineType.APP:
                    resolved_type = "APP"
                else:
                    resolved_type = "ETL"  # Default fallback

                logger.info(
                    f"Pipeline {pipeline_id} identified as {resolved_type} pipeline"
                )
                return Response(
                    {
                        "pipeline_id": str(pipeline_id),
                        "pipeline_type": resolved_type,
                        "source": "pipeline",
                        "workflow_id": str(pipeline.workflow_id),
                        "pipeline_name": pipeline.pipeline_name,
                        "active": pipeline.active,
                        "scheduled": pipeline.scheduled,
                    },
                    status=status.HTTP_200_OK,
                )

            except Pipeline.DoesNotExist:
                # Pipeline not found in either model
                logger.warning(
                    f"Pipeline {pipeline_id} not found in APIDeployment or Pipeline models"
                )
                return Response(
                    {
                        "error": "Pipeline not found",
                        "detail": f"Pipeline {pipeline_id} not found in APIDeployment or Pipeline models",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        except Exception as e:
            logger.error(f"Failed to determine pipeline type for {pipeline_id}: {str(e)}")
            return Response(
                {"error": "Failed to determine pipeline type", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BatchStatusUpdateAPIView(APIView):
    """Internal API endpoint for batch status updates.
    Allows updating multiple workflow executions in a single request.
    """

    def post(self, request):
        """Update multiple workflow execution statuses."""
        try:
            updates = request.data.get("updates", [])

            if not updates:
                return Response(
                    {"error": "updates list is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            successful_updates = []
            failed_updates = []

            with transaction.atomic():
                for update in updates:
                    try:
                        execution_id = update.get("execution_id")
                        status_value = update.get("status")

                        if not execution_id or not status_value:
                            failed_updates.append(
                                {
                                    "execution_id": execution_id,
                                    "error": "execution_id and status are required",
                                }
                            )
                            continue

                        # Get workflow execution with organization filtering
                        execution_queryset = WorkflowExecution.objects.filter(
                            id=execution_id
                        )
                        execution_queryset = filter_queryset_by_organization(
                            execution_queryset, request, "workflow__organization"
                        )
                        execution = execution_queryset.get()

                        # Update status
                        execution.status = status_value

                        # Update optional fields
                        if update.get("error_message"):
                            execution.error_message = update["error_message"][
                                :256
                            ]  # Truncate to fit constraint
                        if update.get("total_files") is not None:
                            execution.total_files = update["total_files"]
                        if update.get("execution_time") is not None:
                            execution.execution_time = update["execution_time"]

                        execution.modified_at = timezone.now()
                        execution.save()

                        successful_updates.append(
                            {
                                "execution_id": str(execution.id),
                                "status": execution.status,
                            }
                        )

                    except WorkflowExecution.DoesNotExist:
                        failed_updates.append(
                            {
                                "execution_id": execution_id,
                                "error": "Workflow execution not found",
                            }
                        )
                    except Exception as e:
                        failed_updates.append(
                            {"execution_id": execution_id, "error": str(e)}
                        )

            logger.info(
                f"Batch status update completed: {len(successful_updates)} successful, {len(failed_updates)} failed"
            )

            return Response(
                {
                    "successful_updates": successful_updates,
                    "failed_updates": failed_updates,
                    "total_processed": len(updates),
                }
            )

        except Exception as e:
            logger.error(f"Failed to process batch status update: {str(e)}")
            return Response(
                {"error": "Failed to process batch status update", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkflowExecutionCleanupAPIView(APIView):
    """Internal API endpoint for cleaning up workflow execution resources."""

    def post(self, request):
        """Cleanup resources for multiple workflow executions."""
        try:
            execution_ids = request.data.get("execution_ids", [])
            cleanup_types = request.data.get("cleanup_types", ["cache", "temp_files"])

            if not execution_ids:
                return Response(
                    {"error": "execution_ids list is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cleaned_executions = []
            failed_cleanups = []

            for execution_id in execution_ids:
                try:
                    # Get workflow execution with organization filtering
                    execution_queryset = WorkflowExecution.objects.filter(id=execution_id)
                    execution_queryset = filter_queryset_by_organization(
                        execution_queryset, request, "workflow__organization"
                    )
                    execution = execution_queryset.get()

                    # Perform cleanup based on cleanup_types
                    cleanup_results = {}

                    if "cache" in cleanup_types:
                        # Clean execution cache
                        try:
                            from workflow_manager.execution.execution_cache_utils import (
                                ExecutionCacheUtils,
                            )

                            ExecutionCacheUtils.cleanup_execution_cache(str(execution.id))
                            cleanup_results["cache"] = "cleaned"
                        except Exception as cache_error:
                            cleanup_results["cache"] = f"error: {str(cache_error)}"

                    if "temp_files" in cleanup_types:
                        # Clean temporary files
                        try:
                            # Import filesystem utilities
                            from unstract.filesystem import FileStorageType, FileSystem

                            # Clean execution directory
                            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
                            file_storage = file_system.get_file_storage()

                            org_id = (
                                execution.workflow.organization_id
                                if execution.workflow
                                else "default"
                            )
                            execution_dir = f"unstract/execution/{org_id}/{execution.workflow_id}/{execution.id}"

                            if file_storage.exists(execution_dir):
                                file_storage.delete(execution_dir)
                                cleanup_results["temp_files"] = "cleaned"
                            else:
                                cleanup_results["temp_files"] = "not_found"

                        except Exception as file_error:
                            cleanup_results["temp_files"] = f"error: {str(file_error)}"

                    cleaned_executions.append(
                        {
                            "execution_id": str(execution.id),
                            "cleanup_results": cleanup_results,
                        }
                    )

                except WorkflowExecution.DoesNotExist:
                    failed_cleanups.append(
                        {
                            "execution_id": execution_id,
                            "error": "Workflow execution not found",
                        }
                    )
                except Exception as e:
                    failed_cleanups.append(
                        {"execution_id": execution_id, "error": str(e)}
                    )

            logger.info(
                f"Cleanup completed: {len(cleaned_executions)} successful, {len(failed_cleanups)} failed"
            )

            return Response(
                {
                    "cleaned_executions": cleaned_executions,
                    "failed_cleanups": failed_cleanups,
                    "total_processed": len(execution_ids),
                }
            )

        except Exception as e:
            logger.error(f"Failed to process cleanup request: {str(e)}")
            return Response(
                {"error": "Failed to process cleanup request", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkflowExecutionMetricsAPIView(APIView):
    """Internal API endpoint for getting workflow execution metrics."""

    def get(self, request):
        """Get execution metrics with optional filtering."""
        try:
            # Get query parameters
            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")
            workflow_id = request.query_params.get("workflow_id")
            status = request.query_params.get("status")

            # Build base queryset with organization filtering
            executions = WorkflowExecution.objects.all()
            executions = filter_queryset_by_organization(
                executions, request, "workflow__organization"
            )

            # Apply filters
            if start_date:
                from datetime import datetime

                executions = executions.filter(
                    created_at__gte=datetime.fromisoformat(start_date)
                )
            if end_date:
                from datetime import datetime

                executions = executions.filter(
                    created_at__lte=datetime.fromisoformat(end_date)
                )
            if workflow_id:
                executions = executions.filter(workflow_id=workflow_id)
            if status:
                executions = executions.filter(status=status)

            # Calculate metrics
            from django.db.models import Avg, Count, Sum

            total_executions = executions.count()

            # Status breakdown
            status_counts = executions.values("status").annotate(count=Count("id"))
            status_breakdown = {item["status"]: item["count"] for item in status_counts}

            # Success rate
            completed_count = status_breakdown.get("COMPLETED", 0)
            success_rate = (
                (completed_count / total_executions) if total_executions > 0 else 0
            )

            # Average execution time
            avg_execution_time = (
                executions.aggregate(avg_time=Avg("execution_time"))["avg_time"] or 0
            )

            # Total files processed
            total_files_processed = (
                executions.aggregate(total_files=Sum("total_files"))["total_files"] or 0
            )

            metrics = {
                "total_executions": total_executions,
                "status_breakdown": status_breakdown,
                "success_rate": success_rate,
                "average_execution_time": avg_execution_time,
                "total_files_processed": total_files_processed,
                "filters_applied": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "workflow_id": workflow_id,
                    "status": status,
                },
            }

            logger.info(
                f"Generated execution metrics: {total_executions} executions, {success_rate:.2%} success rate"
            )

            return Response(metrics)

        except Exception as e:
            logger.error(f"Failed to get execution metrics: {str(e)}")
            return Response(
                {"error": "Failed to get execution metrics", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileHistoryBatchCheckView(APIView):
    """Internal API view to check file history in batch for workers.

    This enables file deduplication by checking which files have already been processed.
    """

    def post(self, request):
        """Check file history for a batch of file hashes.

        POST /internal/workflows/{workflow_id}/file-history/batch-check/

        Request body:
        {
            "workflow_id": "uuid",
            "file_hashes": ["hash1", "hash2", ...],
            "organization_id": "uuid"
        }

        Response:
        {
            "processed_file_hashes": ["hash1", "hash3", ...]
        }
        """
        try:
            workflow_id = request.data.get("workflow_id")
            file_hashes = request.data.get("file_hashes", [])
            organization_id = request.data.get("organization_id")

            if not workflow_id or not file_hashes:
                return Response(
                    {"error": "workflow_id and file_hashes are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Set organization context if provided
            if organization_id:
                StateStore.set(Account.ORGANIZATION_ID, organization_id)

            # Get workflow
            try:
                workflow = filter_queryset_by_organization(
                    Workflow.objects.all(), request, "organization"
                ).get(id=workflow_id)
            except Workflow.DoesNotExist:
                return Response(
                    {"error": "Workflow not found or access denied"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Check file history for the provided hashes
            from workflow_manager.workflow_v2.models.file_history import FileHistory

            # Apply organization filtering to FileHistory query
            file_history_queryset = FileHistory.objects.filter(
                workflow=workflow,
                cache_key__in=file_hashes,
                status="COMPLETED",  # Only consider successfully completed files
            )

            # Apply organization filtering through workflow relationship
            file_history_queryset = filter_queryset_by_organization(
                file_history_queryset, request, "workflow__organization"
            )

            # Get full file history details for cached results
            file_histories = file_history_queryset.values(
                "cache_key",
                "result",
                "metadata",
                "error",
                "file_path",
                "provider_file_uuid",
            )

            # Build response with both processed hashes (for compatibility) and full details
            processed_file_hashes = []
            file_history_details = {}

            for fh in file_histories:
                cache_key = fh["cache_key"]
                processed_file_hashes.append(cache_key)
                file_history_details[cache_key] = {
                    "result": fh["result"],
                    "metadata": fh["metadata"],
                    "error": fh["error"],
                    "file_path": fh["file_path"],
                    "provider_file_uuid": fh["provider_file_uuid"],
                }

            logger.info(
                f"File history batch check: {len(processed_file_hashes)}/{len(file_hashes)} files already processed"
            )

            return Response(
                {
                    "processed_file_hashes": processed_file_hashes,  # For backward compatibility
                    "file_history_details": file_history_details,  # Full details for cached results
                }
            )

        except Exception as e:
            logger.error(f"File history batch check failed: {str(e)}")
            return Response(
                {"error": "File history batch check failed", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileHistoryCreateView(APIView):
    """Internal API view to create file history entries for workers.

    This enables workers to create file history entries after successful processing.
    """

    def post(self, request):
        """Create a file history entry.

        POST /internal/workflow-manager/file-history/create/

        Request body:
        {
            "workflow_id": "uuid",
            "cache_key": "file_hash",
            "provider_file_uuid": "uuid_or_null",
            "file_path": "path/to/file",
            "file_name": "filename.ext",
            "status": "COMPLETED",
            "result": "execution_result",
            "error": "error_message_or_empty",
            "metadata": {},
            "organization_id": "uuid"
        }

        Response:
        {
            "created": true,
            "file_history_id": "uuid"
        }
        """
        try:
            workflow_id = request.data.get("workflow_id")
            cache_key = request.data.get("cache_key")
            organization_id = request.data.get("organization_id")
            provider_file_uuid = request.data.get("provider_file_uuid")
            file_path = request.data.get("file_path")
            file_name = request.data.get("file_name")
            file_size = request.data.get("file_size")
            file_hash = request.data.get("file_hash")
            mime_type = request.data.get("mime_type")
            is_api = request.data.get("is_api")
            status = request.data.get("status")
            result = request.data.get("result")
            error = request.data.get("error")
            metadata = request.data.get("metadata")

            logger.info(
                f"File history create: workflow_id={workflow_id}, cache_key={cache_key}, organization_id={organization_id}"
            )

            if not workflow_id or not cache_key:
                return Response(
                    {"error": "workflow_id and cache_key are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Set organization context if provided
            if organization_id:
                StateStore.set(Account.ORGANIZATION_ID, organization_id)

            # Get workflow
            try:
                workflow = filter_queryset_by_organization(
                    Workflow.objects.all(), request, "organization"
                ).get(id=workflow_id)
            except Workflow.DoesNotExist:
                return Response(
                    {"error": "Workflow not found or access denied"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Create file history entry using the FileHistoryHelper
            from unstract.core.data_models import FileHashData
            from workflow_manager.workflow_v2.enums import ExecutionStatus
            from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper

            # Create FileHashData object from request data using shared class
            file_hash = FileHashData(
                file_name=file_name,
                file_path=file_path,
                file_hash=cache_key,
                file_size=file_size,
                mime_type=mime_type,
                provider_file_uuid=provider_file_uuid,
                fs_metadata={},
                source_connection_type="",
                file_destination="",
                is_executed=False,
                file_number=None,
                connector_metadata={},
                connector_id=None,
                use_file_history=True,
            )

            # Check if file history should be created based on use_file_history flag
            # if not file_hash.use_file_history:
            #     logger.info(
            #         f"Skipping file history creation for {file_hash.file_name} - use_file_history=False"
            #     )
            #     return Response({"created": False, "reason": "use_file_history=False"})

            # Map string status to ExecutionStatus enum
            status_str = request.data.get("status", "COMPLETED")
            try:
                execution_status = ExecutionStatus[status_str]
            except KeyError:
                execution_status = ExecutionStatus.COMPLETED

            # Create file history entry
            file_history = FileHistoryHelper.create_file_history(
                file_hash=file_hash,
                workflow=workflow,
                status=execution_status,
                result=result,
                metadata=metadata,
                error=error,
                is_api=is_api,
            )

            logger.info(
                f"Created file history entry {file_history.id} for file {file_name}"
            )

            return Response({"created": True, "file_history_id": str(file_history.id)})

        except Exception as e:
            logger.error(f"File history creation failed: {str(e)}")
            return Response(
                {"error": "File history creation failed", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PipelineNameAPIView(APIView):
    """Internal API endpoint for fetching pipeline names from models.

    This endpoint fetches the actual pipeline name from Pipeline.pipeline_name
    or APIDeployment.api_name based on the pipeline ID.

    Used by callback workers to get correct pipeline names for notifications.
    """

    def get(self, request, pipeline_id):
        """Fetch pipeline name from Pipeline or APIDeployment model."""
        try:
            from api_v2.models import APIDeployment
            from pipeline_v2.models import Pipeline

            organization_id = getattr(request, "organization_id", None)
            if organization_id:
                StateStore.set(Account.ORGANIZATION_ID, organization_id)

            # First check if this is an API deployment
            try:
                api_deployment = APIDeployment.objects.get(id=pipeline_id)
                logger.info(
                    f"Found API deployment {pipeline_id}: name='{api_deployment.api_name}'"
                )
                # Verify organization access
                if (
                    organization_id
                    and str(api_deployment.organization.organization_id)
                    != organization_id
                ):
                    logger.warning(
                        f"API deployment {pipeline_id} not found in organization {organization_id}"
                    )
                    return Response(
                        {"error": "API deployment not found in organization"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                logger.info(
                    f"Found API deployment {pipeline_id}: name='{api_deployment.api_name}'"
                )
                return Response(
                    {
                        "pipeline_id": str(pipeline_id),
                        "pipeline_name": api_deployment.api_name,
                        "pipeline_type": "API",
                        "source": "api_deployment",
                        "display_name": api_deployment.display_name,
                    }
                )

            except APIDeployment.DoesNotExist:
                pass

            # Check Pipeline model
            try:
                pipeline = Pipeline.objects.get(id=pipeline_id)

                # Verify organization access
                if (
                    organization_id
                    and str(pipeline.organization.organization_id) != organization_id
                ):
                    logger.warning(
                        f"Pipeline {pipeline_id} not found in organization {organization_id}"
                    )
                    return Response(
                        {"error": "Pipeline not found in organization"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                logger.info(
                    f"Found Pipeline {pipeline_id}: name='{pipeline.pipeline_name}', type='{pipeline.pipeline_type}'"
                )
                return Response(
                    {
                        "pipeline_id": str(pipeline_id),
                        "pipeline_name": pipeline.pipeline_name,
                        "pipeline_type": pipeline.pipeline_type,
                        "source": "pipeline",
                        "workflow_id": str(pipeline.workflow_id)
                        if pipeline.workflow
                        else None,
                    }
                )

            except Pipeline.DoesNotExist:
                logger.warning(
                    f"Pipeline {pipeline_id} not found in Pipeline model either"
                )
                pass

            # Not found in either model
            return Response(
                {
                    "error": "Pipeline not found",
                    "detail": f"Pipeline {pipeline_id} not found in APIDeployment or Pipeline models",
                    "pipeline_id": str(pipeline_id),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:
            logger.error(f"Error fetching pipeline name for {pipeline_id}: {str(e)}")
            return Response(
                {
                    "error": "Failed to fetch pipeline name",
                    "detail": str(e),
                    "pipeline_id": str(pipeline_id),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
