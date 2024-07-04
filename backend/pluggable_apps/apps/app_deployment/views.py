import logging
from typing import Any, Optional

from django.db.models.query import QuerySet
from django.http import HttpRequest
from permissions.permission import IsOwner, IsOwnerOrSharedUser
from pluggable_apps.apps.app_deployment.app_deployment_helper import AppDeploymentHelper
from pluggable_apps.apps.app_deployment.models import AppDeployment
from pluggable_apps.apps.app_deployment.serializers import (
    AppDeploymentListSerializer,
    AppDeploymentSerializer,
    IndexedDocumentsSerializer,
    SharedUserListSerializer,
)
from pluggable_apps.apps.canned_question.serializers import CannedQuestionSerializer
from pluggable_apps.apps.chat_history.serializer import ChatHistorySerializer
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from utils.user_session import UserSessionUtils

from unstract.flags.feature_flag import check_feature_flag_status

Logger = logging.getLogger(__name__)


# Create your views here.
class AppDeploymentView(viewsets.ModelViewSet):
    """APP deployment view.

    Args:
        viewsets (_type_): _description_

    Raises:
        InvalidAPIRequest: _description_
        ApiDeploymentBadRequestException: _description_

    Returns:
        _type_: _description_
    """

    def check_feature(self):
        """This method checks the feature flag status and returns a response if
        the feature is disabled."""
        if not check_feature_flag_status("app_deployment"):
            return Response(
                {"message": "Feature disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def get_permissions(self) -> list[Any]:

        if self.action in ["list_canned_questions", "list_chats"]:
            return [IsOwnerOrSharedUser()]

        return [IsOwner()]

    def get_queryset(self) -> Optional[QuerySet]:
        return AppDeployment.objects.for_user(self.request.user)

    def get_serializer_class(self) -> ModelSerializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        if self.action in ["list"]:
            return AppDeploymentListSerializer

        return AppDeploymentSerializer

    def create(
        self, request: HttpRequest, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        response = self.check_feature()
        if response:
            return response

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        org_id = UserSessionUtils.get_organization_id(request)

        AppDeploymentHelper.file_upload_app_deployment.delay(
            workflow_id=serializer.validated_data.get("workflow").id,
            app_name=serializer.validated_data.get("app_name"),
            email=request.user.email,
            org_id=org_id,
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(
        self, request: HttpRequest, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:

        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: HttpRequest, pk: Any = None) -> Response:

        app_deployment = self.get_object()

        serialized_instances = SharedUserListSerializer(app_deployment).data

        return Response(serialized_instances)

    @action(detail=True, methods=["get"])
    def fetch_one(self, request: HttpRequest, pk: Optional[str] = None) -> Response:
        """Custom action to fetch a single instance."""
        response = self.check_feature()
        if response:
            return response

        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def list_chats(self, request: HttpRequest, app_id: str) -> Response:
        response = self.check_feature()
        if response:
            return response

        app_deployment: AppDeployment = AppDeployment.objects.get(app_name=app_id)

        self.check_object_permissions(request, app_deployment)

        serialized_instances = ChatHistorySerializer(
            app_deployment.app_deployment_chat_history.all(), many=True
        ).data

        return Response(serialized_instances)

    @action(detail=True, methods=["get"])
    def list_canned_questions(self, request: HttpRequest, app_id: str) -> Response:
        response = self.check_feature()
        if response:
            return response

        app_deployment: AppDeployment = AppDeployment.objects.get(app_name=app_id)
        self.check_object_permissions(request, app_deployment)
        serialized_instances = CannedQuestionSerializer(
            app_deployment.app_deployment_question.all(), many=True
        ).data

        return Response(serialized_instances)

    @action(detail=True, methods=["get"])
    def list_documents(self, request: HttpRequest, app_id: str) -> Response:
        response = self.check_feature()
        if response:
            return response

        app_deployment: AppDeployment = AppDeployment.objects.get(app_name=app_id)
        self.check_object_permissions(request, app_deployment)

        serialized_instances = IndexedDocumentsSerializer(
            app_deployment.indexed_document_app.all(), many=True
        ).data

        return Response(serialized_instances)
