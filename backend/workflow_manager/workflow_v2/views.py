import logging
from typing import Any

from django.conf import settings
from django.db.models.query import QuerySet
from permissions.permission import IsOwner
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from backend.constants import RequestKey
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.endpoint_v2.endpoint_utils import WorkflowEndpointUtils
from workflow_manager.endpoint_v2.source import SourceConnector
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
            WorkflowEndpointUtils.create_endpoints_for_workflow(workflow)
            # NOTE: Add default connector here if needed
        except Exception as e:
            logger.error(f"Error saving workflow to DB: {e}")
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
