import logging
import uuid
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from permissions.permission import IsOwner
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from rest_framework.views import APIView
from utils.filtering import FilterHelper
from utils.organization_utils import filter_queryset_by_organization, resolve_organization

from backend.constants import RequestKey
from unstract.core.data_models import FileHistoryCreateRequest
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.endpoint_v2.endpoint_utils import WorkflowEndpointUtils
from workflow_manager.endpoint_v2.source import SourceConnector
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.internal_serializers import (
    FileBatchCreateSerializer,
    FileBatchResponseSerializer,
    WorkflowExecutionContextSerializer,
    WorkflowExecutionSerializer,
    WorkflowExecutionStatusUpdateSerializer,
    WorkflowFileExecutionSerializer,
)
from workflow_manager.workflow_v2.constants import WorkflowKey
from workflow_manager.workflow_v2.dto import ExecutionResponse
from workflow_manager.workflow_v2.enums import SchemaEntity, SchemaType
from workflow_manager.workflow_v2.exceptions import (
    InternalException,
    WorkflowDoesNotExistError,
    WorkflowGenerationError,
    WorkflowRegenerationError,
)
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.serializers import (
    ExecuteWorkflowResponseSerializer,
    ExecuteWorkflowSerializer,
    WorkflowSerializer,
)
from workflow_manager.workflow_v2.workflow_helper import (
    WorkflowHelper,
    WorkflowSchemaHelper,
)

logger = logging.getLogger(__name__)


def make_execution_response(response: ExecutionResponse) -> Any:
    return ExecuteWorkflowResponseSerializer(response).data


class WorkflowViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]

    def get_queryset(self) -> QuerySet:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.PROJECT,
            WorkflowKey.WF_OWNER,
            WorkflowKey.WF_IS_ACTIVE,
        )
        queryset = (
            Workflow.objects.filter(created_by=self.request.user, **filter_args)
            if filter_args
            else Workflow.objects.filter(created_by=self.request.user)
        )
        order_by = self.request.query_params.get("order_by")
        if order_by == "desc":
            queryset = queryset.order_by("-modified_at")
        elif order_by == "asc":
            queryset = queryset.order_by("modified_at")

        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action == "execute":
            return ExecuteWorkflowSerializer
        else:
            return WorkflowSerializer

    def perform_update(self, serializer: WorkflowSerializer) -> Workflow:
        """To edit a workflow.

        Raises: WorkflowGenerationError
        """
        kwargs = {}

        try:
            workflow = serializer.save(**kwargs)
            return workflow
        except Exception as e:
            logger.error(f"Error saving workflow to DB: {e}")
            raise WorkflowRegenerationError

    def perform_create(self, serializer: WorkflowSerializer) -> Workflow:
        """To create a new workflow. Creates the Workflow instance first and
        uses it to generate the tool instances.

        Raises: WorkflowGenerationError
        """
        workflow = serializer.save(
            is_active=True,
        )
        try:
            # Create empty WorkflowEndpoints for UI compatibility
            # ConnectorInstances will be created when users actually configure connectors
            WorkflowEndpointUtils.create_endpoints_for_workflow(workflow)
        except Exception as e:
            logger.error(f"Error creating workflow endpoints: {e}")
            raise WorkflowGenerationError
        return workflow

    def get_execution(self, request: Request, pk: str) -> Response:
        execution = WorkflowHelper.get_current_execution(pk)
        return Response(make_execution_response(execution), status=status.HTTP_200_OK)

    def get_workflow_by_id(
        self,
        workflow_id: str | None = None,
    ) -> Workflow:
        """Retrieve workflow by workflow id.

        Args:
            workflow_id (Optional[str], optional): workflow Id.

        Raises:
            WorkflowDoesNotExistError: Raised when workflow_id is not provided or workflow doesn't exist.

        Returns:
            Workflow: workflow
        """
        if workflow_id:
            workflow = WorkflowHelper.get_workflow_by_id(workflow_id)
        else:
            raise WorkflowDoesNotExistError()
        return workflow

    def execute(
        self,
        request: Request,
        pipeline_guid: str | None = None,
    ) -> Response:
        self.serializer_class = ExecuteWorkflowSerializer
        serializer = ExecuteWorkflowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workflow_id = serializer.get_workflow_id(serializer.validated_data)
        execution_id = serializer.get_execution_id(serializer.validated_data)
        execution_action = serializer.get_execution_action(serializer.validated_data)
        file_objs = request.FILES.getlist("files")
        use_file_history: bool = True

        hashes_of_files: dict[str, FileHash] = {}
        if file_objs and execution_id and workflow_id:
            use_file_history = False
            hashes_of_files = SourceConnector.add_input_file_to_api_storage(
                pipeline_id=pipeline_guid,
                workflow_id=workflow_id,
                execution_id=execution_id,
                file_objs=file_objs,
                use_file_history=False,
            )

        try:
            workflow = self.get_workflow_by_id(workflow_id=workflow_id)
            execution_response = self.execute_workflow(
                workflow=workflow,
                execution_action=execution_action,
                execution_id=execution_id,
                pipeline_guid=pipeline_guid,
                hash_values_of_files=hashes_of_files,
                use_file_history=use_file_history,
            )
            if (
                execution_response.execution_status == "ERROR"
                and execution_response.result
                and execution_response.result[0].get("error")
            ):
                raise InternalException(execution_response.result[0].get("error"))
            return Response(
                make_execution_response(execution_response),
                status=status.HTTP_200_OK,
            )
        except Exception as exception:
            logger.error(f"Error while executing workflow: {exception}")
            if file_objs and execution_id and workflow_id:
                DestinationConnector.delete_api_storage_dir(
                    workflow_id=workflow_id, execution_id=execution_id
                )
            raise exception

    def execute_workflow(
        self,
        workflow: Workflow,
        execution_action: str | None = None,
        execution_id: str | None = None,
        pipeline_guid: str | None = None,
        hash_values_of_files: dict[str, FileHash] = {},
        use_file_history: bool = False,
    ) -> ExecutionResponse:
        if execution_action is not None:
            # Step execution
            execution_response = WorkflowHelper.step_execution(
                workflow,
                execution_action,
                execution_id=execution_id,
                hash_values_of_files=hash_values_of_files,
            )
        elif pipeline_guid:
            # pipeline execution
            PipelineProcessor.update_pipeline(
                pipeline_guid, Pipeline.PipelineStatus.INPROGRESS
            )
            execution_response = WorkflowHelper.complete_execution(
                workflow=workflow,
                execution_id=execution_id,
                pipeline_id=pipeline_guid,
                execution_mode=WorkflowExecution.Mode.INSTANT,
                hash_values_of_files=hash_values_of_files,
                use_file_history=use_file_history,
            )
        else:
            execution_response = WorkflowHelper.complete_execution(
                workflow=workflow,
                execution_id=execution_id,
                execution_mode=WorkflowExecution.Mode.INSTANT,
                hash_values_of_files=hash_values_of_files,
                use_file_history=use_file_history,
                timeout=settings.INSTANT_WF_POLLING_TIMEOUT,
            )
        return execution_response

    def activate(self, request: Request, pk: str) -> Response:
        workflow = WorkflowHelper.active_project_workflow(pk)
        serializer = WorkflowSerializer(workflow)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def clear_cache(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        workflow = self.get_object()
        response: dict[str, Any] = WorkflowHelper.clear_cache(workflow_id=workflow.id)
        return Response(response.get("message"), status=response.get("status"))

    @action(detail=True, methods=["get"])
    def can_update(self, request: Request, pk: str) -> Response:
        response: dict[str, Any] = WorkflowHelper.can_update_workflow(pk)
        return Response(response, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def clear_file_marker(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        workflow = self.get_object()
        response: dict[str, Any] = WorkflowHelper.clear_file_marker(
            workflow_id=workflow.id
        )
        return Response(response.get("message"), status=response.get("status"))

    @action(detail=False, methods=["get"])
    def get_schema(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Retrieves the JSON schema for source/destination type modules for
        entities file/API/DB.

        Takes query params `type` (defaults to "src") and
        `entity` (defaults to "file").

        Returns:
            Response: JSON schema for the request made
        """
        schema_type = request.query_params.get("type", SchemaType.SRC.value)
        schema_entity = request.query_params.get("entity", SchemaEntity.FILE.value)

        WorkflowSchemaHelper.validate_request(
            schema_type=SchemaType(schema_type),
            schema_entity=SchemaEntity(schema_entity),
        )
        json_schema = WorkflowSchemaHelper.get_json_schema(
            schema_type=schema_type, schema_entity=schema_entity
        )
        return Response(data=json_schema, status=status.HTTP_200_OK)


# =============================================================================
# INTERNAL API VIEWS - Used by Celery workers for service-to-service communication
# =============================================================================


class WorkflowExecutionInternalViewSet(viewsets.ReadOnlyModelViewSet):
    """Internal API ViewSet for Workflow Execution operations.
    Used by Celery workers for service-to-service communication.
    """

    serializer_class = WorkflowExecutionSerializer
    lookup_field = "id"

    def get_queryset(self):
        """Get workflow executions filtered by organization context."""
        queryset = WorkflowExecution.objects.all()
        return filter_queryset_by_organization(queryset, self.request)

    def retrieve(self, request, *args, **kwargs):
        """Get specific workflow execution with context."""
        try:
            execution = self.get_object()

            # Build comprehensive context
            context_data = {
                "execution": WorkflowExecutionSerializer(execution).data,
                "workflow_definition": execution.workflow.workflow_definition
                if execution.workflow
                else {},
                "source_config": self._get_source_config(execution),
                "destination_config": self._get_destination_config(execution),
                "organization_context": self._get_organization_context(execution),
                "file_executions": WorkflowFileExecutionSerializer(
                    execution.file_executions.all(), many=True
                ).data,
            }

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
        """Get source configuration for execution."""
        try:
            if execution.pipeline_id:
                # Add organization filtering for pipeline lookup
                org_id = getattr(self.request, "organization_id", None)
                if org_id:
                    # Use shared utility to resolve organization
                    organization = resolve_organization(org_id, raise_on_not_found=False)
                    if organization:
                        pipeline = Pipeline.objects.get(
                            id=execution.pipeline_id, organization=organization
                        )
                    else:
                        logger.warning(
                            f"Organization {org_id} not found for pipeline lookup"
                        )
                        return {}
                else:
                    pipeline = Pipeline.objects.get(id=execution.pipeline_id)
                return {
                    "type": "pipeline",
                    "pipeline_id": str(pipeline.id),
                    "source_settings": pipeline.source,
                    "is_api": False,
                }
            else:
                api_deployment = execution.workflow.api_deployments.first()
                if api_deployment:
                    return {
                        "type": "api_deployment",
                        "deployment_id": str(api_deployment.id),
                        "is_api": True,
                    }
            return {}
        except Pipeline.DoesNotExist:
            logger.warning(
                f"Pipeline {execution.pipeline_id} not found for execution {execution.id}"
            )
            return {}
        except Exception as e:
            logger.warning(
                f"Failed to get source config for execution {execution.id}: {str(e)}"
            )
            return {}

    def _get_destination_config(self, execution: WorkflowExecution) -> dict:
        """Get destination configuration for execution."""
        try:
            if execution.pipeline_id:
                # Add organization filtering for pipeline lookup
                org_id = getattr(self.request, "organization_id", None)
                if org_id:
                    # Use shared utility to resolve organization
                    organization = resolve_organization(org_id, raise_on_not_found=False)
                    if organization:
                        pipeline = Pipeline.objects.get(
                            id=execution.pipeline_id, organization=organization
                        )
                    else:
                        logger.warning(
                            f"Organization {org_id} not found for destination pipeline lookup"
                        )
                        return {}
                else:
                    pipeline = Pipeline.objects.get(id=execution.pipeline_id)
                return {"destination_settings": pipeline.destination}
            return {}
        except Pipeline.DoesNotExist:
            logger.warning(
                f"Pipeline {execution.pipeline_id} not found for destination config in execution {execution.id}"
            )
            return {}
        except Exception as e:
            logger.warning(
                f"Failed to get destination config for execution {execution.id}: {str(e)}"
            )
            return {}

    def _get_organization_context(self, execution: WorkflowExecution) -> dict:
        """Get organization context for execution."""
        try:
            return {
                "organization_id": str(execution.organization.id),
                "organization_name": execution.organization.display_name,
                "settings": {},
            }
        except Exception as e:
            logger.warning(
                f"Failed to get organization context for execution {execution.id}: {str(e)}"
            )
            return {}

    @action(detail=True, methods=["post"])
    def status(self, request, id=None):
        """Update workflow execution status."""
        try:
            execution = self.get_object()
            serializer = WorkflowExecutionStatusUpdateSerializer(data=request.data)

            if serializer.is_valid():
                validated_data = serializer.validated_data

                execution.status = validated_data["status"]
                if validated_data.get("error_message"):
                    execution.error_message = validated_data["error_message"]
                if validated_data.get("total_files") is not None:
                    execution.total_files = validated_data["total_files"]
                if validated_data.get("attempts") is not None:
                    execution.attempts = validated_data["attempts"]
                if validated_data.get("execution_time") is not None:
                    execution.execution_time = validated_data["execution_time"]

                execution.modified_at = timezone.now()
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
                {"error": "Failed to update execution status", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FileBatchCreateInternalAPIView(APIView):
    """Internal API endpoint for creating file batches for workflow execution.
    Used by Celery workers for service-to-service communication.
    """

    def post(self, request):
        """Create file execution records in batches."""
        print(
            f"request.data: {request.data} +++++++++++++++++FileBatchCreateInternalAPIView++++++++++++++++++++++++++"
        )
        try:
            serializer = FileBatchCreateSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            workflow_execution_id = validated_data["workflow_execution_id"]
            files_data = validated_data["files"]
            is_api = validated_data["is_api"]

            workflow_execution = get_object_or_404(
                WorkflowExecution, id=workflow_execution_id
            )

            created_file_executions = []

            with transaction.atomic():
                for file_data in files_data:
                    file_hash = FileHash(
                        file_name=file_data["file_name"],
                        file_path=file_data.get("file_path"),
                        file_size=file_data.get("file_size"),
                        file_hash=file_data.get("file_hash"),
                        provider_file_uuid=file_data.get("provider_file_uuid"),
                        mime_type=file_data.get("mime_type"),
                        fs_metadata=file_data.get("fs_metadata"),
                    )

                    file_execution = (
                        WorkflowFileExecution.objects.get_or_create_file_execution(
                            workflow_execution=workflow_execution,
                            file_hash=file_hash,
                            is_api=is_api,
                        )
                    )

                    created_file_executions.append(file_execution)

            batch_id = str(uuid.uuid4())

            response_data = {
                "batch_id": batch_id,
                "workflow_execution_id": workflow_execution_id,
                "total_files": len(created_file_executions),
                "created_file_executions": WorkflowFileExecutionSerializer(
                    created_file_executions, many=True
                ).data,
            }

            response_serializer = FileBatchResponseSerializer(response_data)

            logger.info(
                f"Created file batch {batch_id} with {len(created_file_executions)} files for execution {workflow_execution_id}"
            )

            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Failed to create file batch: {str(e)}")
            return Response(
                {"error": "Failed to create file batch", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# =============================================================================
# FILE HISTORY INTERNAL API VIEWS
# =============================================================================


@api_view(["GET"])
def file_history_by_cache_key_internal(request, cache_key):
    """Get file history by cache key for internal API calls.

    This replaces the FileHistoryHelper.get_file_history() calls in heavy workers.
    """
    try:
        from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper

        organization_id = getattr(request, "organization_id", None)

        # Extract parameters from query string
        workflow_id = request.GET.get("workflow_id")
        file_path = request.GET.get("file_path")

        print(f"workflow_id: {workflow_id}")
        print(f"file_path: {file_path}")
        print(f"organization_id: {organization_id}")
        if not workflow_id:
            return Response(
                {"error": "workflow_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get workflow to pass to helper
        try:
            workflow = Workflow.objects.get(pk=workflow_id)
            print(f"workflow: {workflow}")
            print(f"workflow.organization: {workflow.organization}")
            print(
                f"workflow.organization.organization_id: {workflow.organization.organization_id}"
            )
            if (
                organization_id
                and workflow.organization.organization_id != organization_id
            ):
                return Response(
                    {"error": "Workflow not found in organization"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except Workflow.DoesNotExist:
            return Response(
                {"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Get file history using existing helper
        file_history = FileHistoryHelper.get_file_history(
            workflow=workflow, cache_key=cache_key, file_path=file_path
        )

        if file_history:
            from workflow_manager.workflow_v2.serializers import FileHistorySerializer

            serializer = FileHistorySerializer(file_history)

            return Response(
                {"found": True, "cache_key": cache_key, "file_history": serializer.data},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"found": False, "cache_key": cache_key, "file_history": None},
                status=status.HTTP_200_OK,
            )

    except Exception as e:
        logger.error(f"Failed to get file history for cache key {cache_key}: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def create_file_history_internal(request):
    """Create file history record for internal API calls.

    Workers should check file history exists first via get_file_history API.
    This API assumes pre-checking and only creates when confirmed not to exist.
    """
    try:
        from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper

        organization_id = getattr(request, "organization_id", None)

        # Extract parameters from request data
        data = request.data
        workflow_id = data.get("workflow_id")
        file_hash_data = data.get("file_hash", {})
        is_api = data.get("is_api", False)

        # Extract required parameters for FileHistoryHelper.create_file_history
        execution_status = data.get("status", "COMPLETED")
        result = data.get("result", "")
        metadata = data.get("metadata", "")
        error = data.get("error")

        if not workflow_id:
            return Response(
                {"error": "workflow_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get workflow
        try:
            workflow = Workflow.objects.get(pk=workflow_id)
            if (
                organization_id
                and workflow.organization.organization_id != organization_id
            ):
                return Response(
                    {"error": "Workflow not found in organization"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except Workflow.DoesNotExist:
            return Response(
                {"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Create FileHash object from data
        file_hash = FileHash(
            file_path=file_hash_data.get("file_path"),
            file_name=file_hash_data.get("file_name"),
            source_connection_type=file_hash_data.get("source_connection_type"),
            file_hash=file_hash_data.get("file_hash"),
            file_size=file_hash_data.get("file_size"),
            provider_file_uuid=file_hash_data.get("provider_file_uuid"),
            mime_type=file_hash_data.get("mime_type"),
            fs_metadata=file_hash_data.get("fs_metadata"),
            file_destination=file_hash_data.get("file_destination"),
            is_executed=file_hash_data.get("is_executed"),
            file_number=file_hash_data.get("file_number"),
        )

        # Import ExecutionStatus enum
        from workflow_manager.workflow_v2.enums import ExecutionStatus

        # Convert string status to ExecutionStatus enum
        try:
            status_enum = ExecutionStatus(execution_status)
        except ValueError:
            status_enum = ExecutionStatus.COMPLETED  # Default fallback

        # Create file history using existing helper
        # IntegrityError will propagate as genuine error since worker should have checked first
        file_history_record = FileHistoryHelper.create_file_history(
            file_hash=file_hash,
            workflow=workflow,
            status=status_enum,
            result=result,
            metadata=metadata,
            error=error,
            is_api=is_api,
        )

        if not file_history_record:
            # Helper returned None, this should not happen with our improved get-or-create logic
            # But if it does, try to retrieve the existing record instead of failing
            logger.warning(
                f"create_file_history returned None for workflow {workflow_id} - attempting to retrieve existing record"
            )

            # Try to find the existing record that caused the constraint violation
            try:
                from workflow_manager.workflow_v2.file_history_helper import (
                    FileHistoryHelper,
                )

                existing_record = FileHistoryHelper.get_file_history(
                    workflow=workflow,
                    cache_key=file_hash.file_hash,
                    provider_file_uuid=file_hash.provider_file_uuid,
                    file_path=file_hash.file_path,
                )

                if existing_record:
                    logger.info(
                        f"Retrieved existing file history record for workflow {workflow_id}: {existing_record.id}"
                    )
                    file_history_record = existing_record
                else:
                    # This is a genuine error - we couldn't create or find the record
                    logger.error(
                        f"Failed to create or find file history for workflow {workflow_id}"
                    )
                    return Response(
                        {
                            "error": "Failed to create file history record",
                            "detail": "Unable to create or retrieve file history record",
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

            except Exception as retrieval_error:
                logger.error(
                    f"Failed to retrieve existing file history record: {str(retrieval_error)}"
                )
                return Response(
                    {
                        "error": "Failed to create file history record",
                        "detail": str(retrieval_error),
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        logger.info(
            f"Created file history record for workflow {workflow_id}: {file_history_record.id}"
        )

        # Convert Django model to dataclass for consistent API response
        from unstract.core.data_models import FileHistoryData

        file_history_data = FileHistoryData(
            id=str(file_history_record.id),
            workflow_id=str(workflow_id),
            cache_key=file_history_record.cache_key,
            provider_file_uuid=file_history_record.provider_file_uuid,
            status=file_history_record.status.value
            if hasattr(file_history_record.status, "value")
            else str(file_history_record.status),
            result=file_history_record.result,
            metadata=file_history_record.metadata,
            error=file_history_record.error,
            file_path=file_hash.file_path,
            created_at=file_history_record.created_at,
            modified_at=file_history_record.modified_at,
        )

        # Use FileHistoryCreateRequest for consistent response format
        response = FileHistoryCreateRequest(
            status="created",
            workflow_id=workflow_id,
            file_history=file_history_data,
            message="File history record created successfully",
        )

        return Response(response.to_dict(), status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"Failed to create file history: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def reserve_file_processing_internal(request):
    """Atomic check-and-reserve operation for file processing deduplication.

    This endpoint handles the race condition by atomically checking if a file
    should be processed and reserving it if not already processed/reserved.

    Returns:
        - 200: File already processed (with existing result)
        - 201: File reserved for processing (worker should proceed)
        - 409: File already reserved by another worker (worker should skip)
    """
    try:
        from django.utils import timezone

        from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper

        organization_id = getattr(request, "organization_id", None)
        data = request.data

        workflow_id = data.get("workflow_id")
        cache_key = data.get("cache_key")
        provider_file_uuid = data.get("provider_file_uuid")
        file_path = data.get("file_path")
        worker_id = data.get("worker_id")  # Unique worker identifier

        if not workflow_id or not cache_key:
            return Response(
                {"error": "workflow_id and cache_key are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get workflow
        try:
            workflow = Workflow.objects.get(pk=workflow_id)
            if (
                organization_id
                and workflow.organization.organization_id != organization_id
            ):
                return Response(
                    {"error": "Workflow not found in organization"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except Workflow.DoesNotExist:
            return Response(
                {"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if file already has completed history
        existing_history = FileHistoryHelper.get_file_history(
            workflow=workflow,
            cache_key=cache_key,
            provider_file_uuid=provider_file_uuid,
            file_path=file_path,
        )

        from workflow_manager.workflow_v2.enums import ExecutionStatus

        if existing_history and existing_history.status == ExecutionStatus.COMPLETED:
            # File already processed - return existing result
            logger.info(
                f"File already processed: cache_key={cache_key}, workflow={workflow_id}"
            )

            from unstract.core.data_models import FileHistoryData

            file_history_data = FileHistoryData(
                id=str(existing_history.id),
                workflow_id=str(workflow_id),
                cache_key=existing_history.cache_key,
                provider_file_uuid=existing_history.provider_file_uuid,
                status=existing_history.status.value
                if hasattr(existing_history.status, "value")
                else str(existing_history.status),
                result=existing_history.result,
                metadata=existing_history.metadata,
                error=existing_history.error,
                file_path=existing_history.file_path,
                created_at=existing_history.created_at,
                modified_at=existing_history.modified_at,
            )

            return Response(
                {
                    "reserved": False,
                    "already_processed": True,
                    "file_history": file_history_data.to_dict(),
                    "message": "File already processed, use existing result",
                },
                status=status.HTTP_200_OK,
            )

        # Use Django's get_or_create for atomic reservation
        from workflow_manager.workflow_v2.enums import ExecutionStatus
        from workflow_manager.workflow_v2.models.file_history import FileHistory

        reservation_data = {
            "workflow": workflow,
            "cache_key": cache_key,
            "provider_file_uuid": provider_file_uuid,
            "status": ExecutionStatus.PENDING,  # Use PENDING as reservation status
            "result": f"Reserved by worker {worker_id}",
            "metadata": f"Processing reserved at {timezone.now()}",
            "error": "",
            "file_path": file_path,
        }

        try:
            # Atomic get_or_create operation
            file_history, created = FileHistory.objects.get_or_create(
                workflow=workflow,
                cache_key=cache_key,
                provider_file_uuid=provider_file_uuid,
                file_path=file_path,
                defaults=reservation_data,
            )

            if created:
                # Successfully reserved for this worker
                logger.info(
                    f"Reserved file for processing: cache_key={cache_key}, worker={worker_id}, workflow={workflow_id}"
                )
                return Response(
                    {
                        "reserved": True,
                        "file_history_id": str(file_history.id),
                        "message": "File reserved for processing",
                    },
                    status=status.HTTP_201_CREATED,
                )
            else:
                # File already reserved/processed by another worker
                if file_history.status == ExecutionStatus.COMPLETED:
                    # Another worker completed it while we were checking
                    logger.info(
                        f"File completed by another worker: cache_key={cache_key}, workflow={workflow_id}"
                    )

                    from unstract.core.data_models import FileHistoryData

                    file_history_data = FileHistoryData(
                        id=str(file_history.id),
                        workflow_id=str(workflow_id),
                        cache_key=file_history.cache_key,
                        provider_file_uuid=file_history.provider_file_uuid,
                        status=file_history.status.value
                        if hasattr(file_history.status, "value")
                        else str(file_history.status),
                        result=file_history.result,
                        metadata=file_history.metadata,
                        error=file_history.error,
                        file_path=file_history.file_path,
                        created_at=file_history.created_at,
                        modified_at=file_history.modified_at,
                    )

                    return Response(
                        {
                            "reserved": False,
                            "already_processed": True,
                            "file_history": file_history_data.to_dict(),
                            "message": "File completed by another worker",
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    # File reserved by another worker (PENDING status)
                    logger.info(
                        f"File already reserved by another worker: cache_key={cache_key}, workflow={workflow_id}"
                    )
                    return Response(
                        {
                            "reserved": False,
                            "already_reserved": True,
                            "message": "File already reserved by another worker",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

        except Exception as e:
            logger.error(f"Failed to reserve file for processing: {str(e)}")
            return Response(
                {"error": "Failed to reserve file for processing", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    except Exception as e:
        logger.error(f"Failed to process reservation request: {str(e)}")
        return Response(
            {"error": "Internal server error", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def get_file_history_internal(request):
    """Get file history for worker deduplication using backend FileHistoryHelper.

    This endpoint exposes the same FileHistoryHelper.get_file_history() logic
    used by the backend source.py to ensure consistent deduplication behavior.
    """
    try:
        workflow_id = request.data.get("workflow_id")
        provider_file_uuid = request.data.get("provider_file_uuid")
        file_hash = request.data.get("file_hash")  # Also accept file_hash (cache_key)
        file_path = request.data.get("file_path")
        organization_id = request.data.get("organization_id")

        # Must have either provider_file_uuid or file_hash
        if (
            not workflow_id
            or not organization_id
            or (not provider_file_uuid and not file_hash)
        ):
            return Response(
                {
                    "error": "Missing required parameters",
                    "required": [
                        "workflow_id",
                        "organization_id",
                        "either provider_file_uuid or file_hash",
                    ],
                    "optional": ["file_path"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            f"Getting file history for workflow {workflow_id}, provider_uuid: {provider_file_uuid}, "
            f"file_hash: {file_hash}, file_path: {file_path}"
        )
        logger.info(f"Organization ID from request: {organization_id}")

        # Get workflow
        try:
            workflow = Workflow.objects.get(
                id=workflow_id, organization__organization_id=organization_id
            )
            logger.info(
                f"Found workflow {workflow_id} with organization {workflow.organization.organization_id}"
            )
        except Workflow.DoesNotExist:
            return Response(
                {"error": "Workflow not found", "workflow_id": workflow_id},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Use the same FileHistoryHelper logic as backend source.py:566-570
        from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper

        logger.info(
            f"Calling FileHistoryHelper.get_file_history with workflow={workflow.id}, "
            f"cache_key={file_hash}, provider_file_uuid={provider_file_uuid}, file_path={file_path}"
        )
        # Pass file_hash as cache_key to FileHistoryHelper
        file_history = FileHistoryHelper.get_file_history(
            workflow=workflow,
            cache_key=file_hash,  # Use file_hash as cache_key
            provider_file_uuid=provider_file_uuid,
            file_path=file_path,
        )
        logger.info(f"FileHistoryHelper returned: {file_history}")

        if file_history:
            # Convert to dictionary for JSON response
            file_history_data = {
                "id": str(file_history.id),
                "workflow_id": str(file_history.workflow_id),
                "cache_key": file_history.cache_key,
                "provider_file_uuid": file_history.provider_file_uuid,
                "file_path": file_history.file_path,
                "status": file_history.status,
                "is_completed": file_history.is_completed(),
                "created_at": file_history.created_at.isoformat()
                if file_history.created_at
                else None,
                "completed_at": file_history.modified_at.isoformat()
                if file_history.modified_at
                else None,
            }

            logger.info(
                f"File history found for {file_path}: status={file_history.status}, completed={file_history.is_completed()}"
            )

            return Response(
                {"file_history": file_history_data, "found": True},
                status=status.HTTP_200_OK,
            )
        else:
            logger.info(
                f"No file history found for {file_path} with provider_uuid: {provider_file_uuid}"
            )
            return Response(
                {"file_history": None, "found": False}, status=status.HTTP_200_OK
            )

    except Exception as e:
        logger.error(f"Failed to get file history: {str(e)}")
        return Response(
            {"error": "Failed to get file history", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def file_history_status_internal(request, file_history_id):
    """Get file history status for internal API calls."""
    try:
        from workflow_manager.workflow_v2.models.file_history import FileHistory

        organization_id = getattr(request, "organization_id", None)

        # Get file history record
        try:
            file_history = FileHistory.objects.get(pk=file_history_id)
            if organization_id and file_history.organization_id != organization_id:
                return Response(
                    {"error": "File history not found in organization"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except FileHistory.DoesNotExist:
            return Response(
                {"error": "File history not found"}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {
                "file_history_id": file_history_id,
                "status": "exists",
                "cache_key": file_history.cache_key,
                "workflow_id": str(file_history.workflow_id),
                "created_at": file_history.created_at.isoformat(),
                "is_api": getattr(file_history, "is_api", False),
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Failed to get file history status for {file_history_id}: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
