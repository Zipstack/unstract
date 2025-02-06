import json
import logging
from typing import Any, Optional

from api_v2.constants import ApiExecution
from api_v2.deployment_helper import DeploymentHelper
from api_v2.exceptions import NoActiveAPIKeyError
from api_v2.models import APIDeployment
from api_v2.postman_collection.dto import PostmanCollection
from api_v2.serializers import (
    APIDeploymentListSerializer,
    APIDeploymentSerializer,
    DeploymentResponseSerializer,
    ExecutionQuerySerializer,
    ExecutionRequestSerializer,
)
from django.db.models import QuerySet
from django.http import HttpResponse
from permissions.permission import IsOwner
from rest_framework import serializers, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from utils.enums import CeleryTaskState
from workflow_manager.workflow_v2.dto import ExecutionResponse

logger = logging.getLogger(__name__)


class DeploymentExecution(views.APIView):
    def initialize_request(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Request:
        """To remove csrf request for public API.

        Args:
            request (Request): _description_

        Returns:
            Request: _description_
        """
        setattr(request, "csrf_processing_done", True)
        return super().initialize_request(request, *args, **kwargs)

    @DeploymentHelper.validate_api_key
    def post(
        self, request: Request, org_name: str, api_name: str, api: APIDeployment
    ) -> Response:
        serializer = ExecutionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_objs = serializer.validated_data.get(ApiExecution.FILES_FORM_DATA)
        timeout = serializer.validated_data.get(ApiExecution.TIMEOUT_FORM_DATA)
        include_metadata = serializer.validated_data.get(ApiExecution.INCLUDE_METADATA)
        include_metrics = serializer.validated_data.get(ApiExecution.INCLUDE_METRICS)
        use_file_history = serializer.validated_data.get(ApiExecution.USE_FILE_HISTORY)
        tag_names = serializer.validated_data.get(ApiExecution.TAGS)
        response = DeploymentHelper.execute_workflow(
            organization_name=org_name,
            api=api,
            file_objs=file_objs,
            timeout=timeout,
            include_metadata=include_metadata,
            include_metrics=include_metrics,
            use_file_history=use_file_history,
            tag_names=tag_names,
        )
        if "error" in response and response["error"]:
            return Response(
                {"message": response},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response({"message": response}, status=status.HTTP_200_OK)

    @DeploymentHelper.validate_api_key
    def get(
        self, request: Request, org_name: str, api_name: str, api: APIDeployment
    ) -> Response:
        serializer = ExecutionQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        execution_id = serializer.validated_data.get(ApiExecution.EXECUTION_ID)
        include_metadata = serializer.validated_data.get(ApiExecution.INCLUDE_METADATA)
        include_metrics = serializer.validated_data.get(ApiExecution.INCLUDE_METRICS)

        # Fetch execution status
        response: ExecutionResponse = DeploymentHelper.get_execution_status(
            execution_id
        )

        # Determine response status
        response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
        if response.execution_status == CeleryTaskState.COMPLETED.value:
            response_status = status.HTTP_200_OK
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

    def get_queryset(self) -> Optional[QuerySet]:
        return APIDeployment.objects.filter(created_by=self.request.user)

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action in ["list"]:
            return APIDeploymentListSerializer
        return APIDeploymentSerializer

    @action(detail=True, methods=["get"])
    def fetch_one(self, request: Request, pk: Optional[str] = None) -> Response:
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
        api_key = DeploymentHelper.create_api_key(
            serializer=serializer, request=request
        )
        response_serializer = DeploymentResponseSerializer(
            {"api_key": api_key.api_key, **serializer.data}
        )

        headers = self.get_success_headers(serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @action(detail=True, methods=["get"])
    def download_postman_collection(
        self, request: Request, pk: Optional[str] = None
    ) -> Response:
        """Downloads a Postman Collection of the API deployment instance."""
        instance = self.get_object()
        api_key_inst = instance.api_keys.filter(is_active=True).first()
        if not api_key_inst:
            logger.error(f"No active API key set for deployment {instance.pk}")
            raise NoActiveAPIKeyError(deployment_name=instance.display_name)

        postman_collection = PostmanCollection.create(
            instance=instance, api_key=api_key_inst.api_key
        )
        response = HttpResponse(
            json.dumps(postman_collection.to_dict()), content_type="application/json"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{instance.display_name}.json"'
        )
        return response
