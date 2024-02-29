import logging
from typing import Any, Optional

from backend.constants import RequestKey
from connector.connector_instance_helper import ConnectorInstanceHelper
from django.conf import settings
from django.db.models.query import QuerySet
from django.http import HttpRequest
from permissions.permission import IsOwner
from pipeline.models import Pipeline
from pipeline.pipeline_processor import PipelineProcessor
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from tool_instance.tool_processor import ToolProcessor
from unstract.tool_registry.dto import Tool
from unstract.tool_registry.tool_registry import ToolRegistry
from utils.filtering import FilterHelper
from workflow_manager.endpoint.destination import DestinationConnector
from workflow_manager.endpoint.endpoint_utils import WorkflowEndpointUtils
from workflow_manager.endpoint.source import SourceConnector
from workflow_manager.workflow.constants import WorkflowKey
from workflow_manager.workflow.dto import ExecutionResponse
from workflow_manager.workflow.enums import SchemaEntity, SchemaType
from workflow_manager.workflow.exceptions import (
    InvalidRequest,
    WorkflowDoesNotExistError,
    WorkflowExecutionBadRequestException,
    WorkflowExecutionError,
    WorkflowGenerationError,
    WorkflowRegenerationError,
    MissingEnvException,
)
from workflow_manager.workflow.generator import WorkflowGenerator
from workflow_manager.workflow.models.workflow import Workflow
from workflow_manager.workflow.serializers import (
    ExecuteWorkflowResponseSerializer,
    ExecuteWorkflowSerializer,
    WorkflowSerializer,
)
from workflow_manager.workflow.workflow_helper import (
    WorkflowHelper,
    WorkflowSchemaHelper,
)

logger = logging.getLogger(__name__)


def update_pipeline(
    pipeline_guid: Optional[str], status: tuple[str, str]
) -> Any:
    if pipeline_guid:
        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(
            pipeline_id=pipeline_guid
        )
        PipelineProcessor.update_pipeline_status(
            pipeline=pipeline, is_end=True, status=status
        )


def make_execution_response(response: ExecutionResponse) -> Any:
    return ExecuteWorkflowResponseSerializer(response).data


def handle_false(string: str) -> bool:
    if string.lower() == "false":
        return False
    else:
        return True


class WorkflowViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    queryset = Workflow.objects.all()

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

    def _generate_workflow(self, workflow_id: str) -> WorkflowGenerator:
        registry_tools: list[Tool] = ToolProcessor.get_registry_tools()
        generator = WorkflowGenerator(workflow_id=workflow_id)
        generator.set_request(self.request)
        generator.generate_workflow(registry_tools)
        return generator

    def perform_update(self, serializer: WorkflowSerializer) -> Workflow:
        """To edit a workflow. Regenerates the tool instances for a new prompt.

        Raises: WorkflowGenerationError
        """
        kwargs = {}
        if serializer.validated_data.get(WorkflowKey.PROMPT_TEXT):
            workflow: Workflow = self.get_object()
            generator = self._generate_workflow(workflow_id=workflow.id)
            kwargs = {
                WorkflowKey.LLM_RESPONSE: generator.llm_response,
                WorkflowKey.WF_IS_ACTIVE: True,
            }
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
        try:
            workflow = serializer.save(
                is_active=True,
            )
            WorkflowEndpointUtils.create_endpoints_for_workflow(workflow)

            # Enable GCS configurations to create GCS while creating a workflow
            if (
                settings.GOOGLE_STORAGE_ACCESS_KEY_ID
                and settings.UNSTRACT_FREE_STORAGE_BUCKET_NAME
            ):
                ConnectorInstanceHelper.create_default_gcs_connector(
                    workflow, self.request.user
                )

        except Exception as e:
            logger.error(f"Error saving workflow to DB: {e}")
            raise WorkflowGenerationError
        return workflow

    def get_execution(self, request: Request, pk: str) -> Response:
        execution = WorkflowHelper.get_current_execution(pk)
        return Response(
            make_execution_response(execution), status=status.HTTP_200_OK
        )

    def get_error_from_serializer(
        self, error_details: dict[str, Any]
    ) -> Optional[str]:
        """Validation error."""
        error_key = next(iter(error_details))
        # Get the first error message
        error_message: str = f"{error_details[error_key][0]} : {error_key}"
        return error_message

    def get_workflow_by_id_or_project_id(
        self,
        workflow_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Workflow:
        """Retrieve workflow  by workflow id or project Id.

        Args:
            workflow_id (Optional[str], optional): workflow Id.
            project_id (Optional[str], optional): Project Id.

        Raises:
            WorkflowDoesNotExistError: _description_

        Returns:
            Workflow: workflow
        """
        if workflow_id:
            workflow = WorkflowHelper.get_workflow_by_id(workflow_id)
        elif project_id:
            workflow = WorkflowHelper.get_active_workflow_by_project_id(
                project_id
            )
        else:
            raise WorkflowDoesNotExistError()
        return workflow

    def execute(
        self,
        request: Request,
        pipeline_guid: Optional[str] = None,
        with_log: Optional[bool] = None,
    ) -> Response:
        if with_log is not None:
            # Handle string field
            with_log = handle_false(str(with_log))

        self.serializer_class = ExecuteWorkflowSerializer
        serializer = ExecuteWorkflowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workflow_id = serializer.get_workflow_id(serializer.validated_data)
        project_id = serializer.get_project_id(serializer.validated_data)
        execution_id = serializer.get_execution_id(serializer.validated_data)
        execution_action = serializer.get_execution_action(
            serializer.validated_data
        )
        file_objs = request.FILES.getlist("files")
        hashes_of_files = {}
        if file_objs and execution_id and workflow_id:
            hashes_of_files = SourceConnector.add_input_file_to_api_storage(
                workflow_id=workflow_id,
                execution_id=execution_id,
                file_objs=file_objs,
            )

        try:
            workflow = self.get_workflow_by_id_or_project_id(
                workflow_id=workflow_id, project_id=project_id
            )
            execution_response = self.execute_workflow(
                workflow=workflow,
                execution_action=execution_action,
                execution_id=execution_id,
                pipeline_guid=pipeline_guid,
                with_log=with_log,
                hash_values_of_files=hashes_of_files,
            )
            return Response(
                make_execution_response(execution_response),
                status=status.HTTP_200_OK,
            )
        except (InvalidRequest, WorkflowExecutionError) as exception:
            logger.error(f"Error while executing workflow: {exception}")
            update_pipeline(pipeline_guid, Pipeline.PipelineStatus.FAILURE)
            raise exception
        except MissingEnvException as exception:
            update_pipeline(pipeline_guid, Pipeline.PipelineStatus.FAILURE)
            logger.error(f"Error while executing workflow: {exception}")
            return Response(
                {
                    "error": "Please check the logs for more details: " + str(exception)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as exception:
            logger.error(f"Error while executing workflow: {exception}")
            update_pipeline(pipeline_guid, Pipeline.PipelineStatus.FAILURE)
            if file_objs and execution_id and workflow_id:
                DestinationConnector.delete_api_storage_dir(
                    workflow_id=workflow_id, execution_id=execution_id
                )
            raise exception

    def execute_workflow(
        self,
        workflow: Workflow,
        execution_action: Optional[str] = None,
        execution_id: Optional[str] = None,
        pipeline_guid: Optional[str] = None,
        with_log: Optional[bool] = None,
        hash_values_of_files: dict[str, str] = {},
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
            update_pipeline(pipeline_guid, Pipeline.PipelineStatus.INPROGRESS)
            execution_response = WorkflowHelper.complete_execution(
                workflow=workflow,
                execution_id=execution_id,
                pipeline_id=pipeline_guid,
                log_required=with_log,
                hash_values_of_files=hash_values_of_files,
            )
            update_pipeline(pipeline_guid, Pipeline.PipelineStatus.SUCCESS)
        else:
            execution_response = WorkflowHelper.complete_execution(
                workflow=workflow,
                execution_id=execution_id,
                log_required=with_log,
                hash_values_of_files=hash_values_of_files,
            )
        return execution_response

    def activate(self, request: Request, pk: str) -> Response:
        workflow = WorkflowHelper.active_project_workflow(pk)
        serializer = WorkflowSerializer(workflow)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def clear_cache(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        workflow = self.get_object()
        response: dict[str, Any] = WorkflowHelper.clear_cache(
            workflow_id=workflow.id
        )
        return Response(response.get("message"), status=response.get("status"))

    @action(detail=True, methods=["get"])
    def clear_file_marker(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        workflow = self.get_object()
        response: dict[str, Any] = WorkflowHelper.clear_file_marker(
            workflow_id=workflow.id
        )
        return Response(response.get("message"), status=response.get("status"))

    @action(detail=False, methods=["get"])
    def get_schema(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """Retrieves the JSON schema for source/destination type modules for
        entities file/API/DB.

        Takes query params `type` (defaults to "src") and
        `entity` (defaults to "file").

        Returns:
            Response: JSON schema for the request made
        """
        schema_type = request.query_params.get("type", SchemaType.SRC.value)
        schema_entity = request.query_params.get(
            "entity", SchemaEntity.FILE.value
        )

        WorkflowSchemaHelper.validate_request(
            schema_type=SchemaType(schema_type),
            schema_entity=SchemaEntity(schema_entity),
        )
        json_schema = WorkflowSchemaHelper.get_json_schema(
            schema_type=schema_type, schema_entity=schema_entity
        )
        return Response(data=json_schema, status=status.HTTP_200_OK)

    @action(detail=True, methods=["GET"])
    def workflow_settings_schema(self, request: HttpRequest) -> Response:
        tool_registry = ToolRegistry()
        schema = tool_registry.get_project_settings_schema()
        return Response(schema)

    @action(detail=True, methods=["GET", "PUT"])
    def workflow_settings(self, request: HttpRequest, pk: str) -> Response:
        workflow = self.get_object()
        tool_registry = ToolRegistry()
        if request.method == "GET":
            schema = tool_registry.get_project_settings_schema()
            return Response({"schema": schema, "settings": workflow.settings})

        elif request.method == "PUT":
            schema = tool_registry.get_project_settings_schema()

            try:
                tool_registry.validate_schema_with_data(request.data, schema)
            except Exception as e:
                logger.error(f"Invalid input data {str(e)}")
                raise WorkflowExecutionBadRequestException("Invalid input")

            workflow.settings = request.data
            workflow.save()
            return Response(
                {"message": "Settings updated successfully"},
                status=status.HTTP_200_OK,
            )
