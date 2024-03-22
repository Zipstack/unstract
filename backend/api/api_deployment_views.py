from typing import Any, Optional

from api.deployment_helper import DeploymentHelper
from api.exceptions import InvalidAPIRequest
from api.models import APIDeployment
from api.serializers import (
    APIDeploymentListSerializer,
    APIDeploymentSerializer,
    DeploymentResponseSerializer,
    ExecutionRequestSerializer,
)
from django.db.models import QuerySet
from permissions.permission import IsOwner
from rest_framework import serializers, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from workflow_manager.workflow.dto import ExecutionResponse


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
        file_objs = request.FILES.getlist("files")
        serializer = ExecutionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        timeout = serializer.get_timeout(serializer.validated_data)

        if not file_objs or len(file_objs) == 0:
            raise InvalidAPIRequest("File shouldn't be empty")
        response = DeploymentHelper.execute_workflow(
            organization_name=org_name,
            api=api,
            file_objs=file_objs,
            timeout=timeout,
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
        execution_id = request.query_params.get("execution_id")
        if not execution_id:
            raise InvalidAPIRequest("execution_id shouldn't be empty")
        response: ExecutionResponse = DeploymentHelper.get_execution_status(
            execution_id=execution_id
        )
        if response.execution_status != "SUCCESS":
            return Response(
                {
                    "status": response.execution_status,
                    "message": response.result,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(
            {"status": response.execution_status, "message": response.result},
            status=status.HTTP_200_OK,
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
        api_key = DeploymentHelper.create_api_key(serializer=serializer)
        response_serializer = DeploymentResponseSerializer(
            {"api_key": api_key.api_key, **serializer.data}
        )

        headers = self.get_success_headers(serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


def get_error_from_serializer(error_details: dict[str, Any]) -> Optional[str]:
    error_key = next(iter(error_details))
    # Get the first error message
    error_message: str = f"{error_details[error_key][0]} : {error_key}"
    return error_message
