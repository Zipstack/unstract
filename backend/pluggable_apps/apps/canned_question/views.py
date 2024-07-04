from typing import Any

from django.db.models.query import QuerySet
from permissions.permission import IsOwnerOrSharedUser
from pluggable_apps.apps.app_deployment.models import AppDeployment
from pluggable_apps.apps.canned_question.models import CannedQuestion
from pluggable_apps.apps.canned_question.serializers import (
    CannedQuestionListSerializer,
    CannedQuestionRequestSerializer,
    CannedQuestionSerializer,
)
from rest_framework import serializers, viewsets
from rest_framework.request import Request
from rest_framework.response import Response


# Create your views here.
class CannedQuestionView(viewsets.ModelViewSet):
    """APP deployment view.

    Args:
        viewsets (_type_): _description_

    Raises:
        InvalidAPIRequest: _description_
        ApiDeploymentBadRequestException: _description_

    Returns:
        _type_: _description_
    """

    queryset = CannedQuestion.objects.all()

    def get_permissions(self) -> list[Any]:

        return [IsOwnerOrSharedUser()]

    def get_queryset(self) -> QuerySet:
        """Adding additional filters and default sorting.

        Returns:
            QuerySet: _description_
        """

        return CannedQuestion.objects.all()

    def get_serializer_class(self) -> serializers.Serializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        if self.action in ["list"]:
            return CannedQuestionListSerializer
        elif self.action in ["create"]:
            return CannedQuestionRequestSerializer
        return CannedQuestionSerializer

    def create(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        """Method for Create new App deployment.

        Args:
            request (Request): _description_

        Raises:
            CannedQuestionBadRequestException: _description_

        Returns:
            Response: _description_
        """
        context = super().get_serializer_context()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app_id = serializer.validated_data.get("app_id")
        app_deployment = AppDeployment.objects.get(app_name=app_id)
        self.check_object_permissions(request, app_deployment)
        question = serializer.validated_data.get("question")

        serializer = CannedQuestionSerializer(
            data={"question": question, "app_deployment": app_deployment.id},
            context=context,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(serializer.data)
