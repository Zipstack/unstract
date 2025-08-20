import json
import logging
from typing import Any

from configuration.models import Configuration
from django.db.models import QuerySet
from django.http import HttpResponse
from permissions.permission import IsOwner
from prompt_studio.prompt_studio_registry_v2.models import PromptStudioRegistry
from rest_framework import serializers, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from tool_instance_v2.models import ToolInstance
from utils.enums import CeleryTaskState
from workflow_manager.workflow_v2.dto import ExecutionResponse

from api_v2.api_deployment_dto_registry import ApiDeploymentDTORegistry
from api_v2.constants import ApiExecution
from api_v2.deployment_helper import DeploymentHelper
from api_v2.dto import DeploymentExecutionDTO
from api_v2.exceptions import NoActiveAPIKeyError
from api_v2.models import APIDeployment
from api_v2.serializers import (
    APIDeploymentListSerializer,
    APIDeploymentSerializer,
    DeploymentResponseSerializer,
    ExecutionQuerySerializer,
    ExecutionRequestSerializer,
)

logger = logging.getLogger(__name__)


class DeploymentExecution(views.APIView):
    def initialize_request(self, request: Request, *args: Any, **kwargs: Any) -> Request:
        """To remove csrf request for public API.

        Args:
            request (Request): _description_

        Returns:
            Request: _description_
        """
        request.csrf_processing_done = True
        return super().initialize_request(request, *args, **kwargs)

    @DeploymentHelper.validate_api_key
    def post(
        self,
        request: Request,
        org_name: str,
        api_name: str,
        deployment_execution_dto: DeploymentExecutionDTO,
    ) -> Response:
        api: APIDeployment = deployment_execution_dto.api
        api_key: str = deployment_execution_dto.api_key
        serializer = ExecutionRequestSerializer(
            data=request.data, context={"api": api, "api_key": api_key}
        )
        serializer.is_valid(raise_exception=True)
        file_objs = serializer.validated_data.get(ApiExecution.FILES_FORM_DATA, [])
        presigned_urls = serializer.validated_data.get(ApiExecution.PRESIGNED_URLS, [])
        timeout = serializer.validated_data.get(ApiExecution.TIMEOUT_FORM_DATA)
        include_metadata = serializer.validated_data.get(ApiExecution.INCLUDE_METADATA)
        include_metrics = serializer.validated_data.get(ApiExecution.INCLUDE_METRICS)
        use_file_history = serializer.validated_data.get(ApiExecution.USE_FILE_HISTORY)
        tag_names = serializer.validated_data.get(ApiExecution.TAGS)
        llm_profile_id = serializer.validated_data.get(ApiExecution.LLM_PROFILE_ID)
        hitl_queue_name = serializer.validated_data.get(ApiExecution.HITL_QUEUE_NAME)

        if presigned_urls:
            DeploymentHelper.load_presigned_files(presigned_urls, file_objs)

        response = DeploymentHelper.execute_workflow(
            organization_name=org_name,
            api=api,
            file_objs=file_objs,
            timeout=timeout,
            include_metadata=include_metadata,
            include_metrics=include_metrics,
            use_file_history=use_file_history,
            tag_names=tag_names,
            llm_profile_id=llm_profile_id,
            hitl_queue_name=hitl_queue_name,
        )
        if "error" in response and response["error"]:
            logger.error("API deployment execution failed")
            return Response(
                {"message": response},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response({"message": response}, status=status.HTTP_200_OK)

    @DeploymentHelper.validate_api_key
    def get(
        self,
        request: Request,
        org_name: str,
        api_name: str,
        deployment_execution_dto: DeploymentExecutionDTO,
    ) -> Response:
        serializer = ExecutionQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        execution_id = serializer.validated_data.get(ApiExecution.EXECUTION_ID)
        include_metadata = serializer.validated_data.get(ApiExecution.INCLUDE_METADATA)
        include_metrics = serializer.validated_data.get(ApiExecution.INCLUDE_METRICS)

        # Fetch execution status
        response: ExecutionResponse = DeploymentHelper.get_execution_status(execution_id)
        # Determine response status
        response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
        if response.execution_status == CeleryTaskState.COMPLETED.value:
            response_status = status.HTTP_200_OK
            # Check if highlight data should be removed using configuration registry
            api_deployment = deployment_execution_dto.api
            organization = api_deployment.organization if api_deployment else None
            enable_highlight = False  # Safe default if the key is unavailable (e.g., OSS)
            # Check if the configuration key exists (Cloud deployment) or use settings (OSS)
            from configuration.config_registry import ConfigurationRegistry

            if ConfigurationRegistry.is_config_key_available(
                "ENABLE_HIGHLIGHT_API_DEPLOYMENT"
            ):
                enable_highlight = Configuration.get_value_by_organization(
                    config_key="ENABLE_HIGHLIGHT_API_DEPLOYMENT",
                    organization=organization,
                )
            if not enable_highlight:
                response.remove_result_metadata_keys(["highlight_data"])
            if not include_metadata:
                response.remove_result_metadata_keys()
            if not include_metrics:
                response.remove_result_metrics()
        if response.result_acknowledged:
            response_status = status.HTTP_406_NOT_ACCEPTABLE
            response.result = "Result already acknowledged"
        return Response(
            data={
                "status": response.execution_status,
                "message": response.result,
            },
            status=response_status,
        )


class APIDeploymentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]

    def get_queryset(self) -> QuerySet | None:
        queryset = APIDeployment.objects.filter(created_by=self.request.user)

        # Filter by workflow ID if provided
        workflow_filter = self.request.query_params.get("workflow", None)
        if workflow_filter:
            queryset = queryset.filter(workflow_id=workflow_filter)

        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action in ["list"]:
            return APIDeploymentListSerializer
        return APIDeploymentSerializer

    @action(detail=True, methods=["get"])
    def fetch_one(self, request: Request, pk: str | None = None) -> Response:
        """Custom action to fetch a single instance."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        serializer: Serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        api_key = DeploymentHelper.create_api_key(serializer=serializer, request=request)
        response_serializer = DeploymentResponseSerializer(
            {"api_key": api_key.api_key, **serializer.data}
        )

        headers = self.get_success_headers(serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @action(detail=False, methods=["get"])
    def by_prompt_studio_tool(self, request: Request) -> Response:
        """Get API deployments for a specific prompt studio tool."""
        tool_id = request.query_params.get("tool_id")
        if not tool_id:
            return Response(
                {"error": "tool_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Find the prompt studio registry for this custom tool
            registry = PromptStudioRegistry.objects.get(custom_tool__tool_id=tool_id)

            # Find workflows that contain tool instances with this prompt registry ID
            tool_instances = ToolInstance.objects.filter(
                tool_id=str(registry.prompt_registry_id)
            )
            workflow_ids = tool_instances.values_list("workflow_id", flat=True).distinct()

            # Get API deployments for these workflows
            deployments = APIDeployment.objects.filter(
                workflow_id__in=workflow_ids, created_by=request.user
            )

            serializer = APIDeploymentListSerializer(deployments, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except PromptStudioRegistry.DoesNotExist:
            return Response([], status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching API deployments for tool {tool_id}: {e}")
            return Response(
                {"error": "Failed to fetch API deployments"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def download_postman_collection(
        self, request: Request, pk: str | None = None
    ) -> Response:
        """Downloads a Postman Collection of the API deployment instance."""
        instance = self.get_object()
        api_key_inst = instance.api_keys.filter(is_active=True).first()
        if not api_key_inst:
            logger.error(f"No active API key set for deployment {instance.pk}")
            raise NoActiveAPIKeyError(deployment_name=instance.display_name)
        dto_class = ApiDeploymentDTORegistry.get_dto()
        postman_collection = dto_class.create(
            instance=instance, api_key=api_key_inst.api_key
        )
        response = HttpResponse(
            json.dumps(postman_collection.to_dict()), content_type="application/json"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{instance.display_name}.json"'
        )
        return response