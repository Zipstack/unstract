from typing import Any

from django.db.models.manager import BaseManager
from django.db.models.query import QuerySet
from permissions.permission import IsOwnerOrSharedUser
from pluggable_apps.apps.app_deployment.models import AppDeployment
from pluggable_apps.apps.chat_history.models import ChatHistory
from pluggable_apps.apps.chat_history.serializer import (
    ChatHistoryListSerializer,
    ChatHistoryRequestSerializer,
    ChatHistorySerializer,
)
from pluggable_apps.apps.chat_transcript.serializer import ChatTranscriptSerializer
from rest_framework import serializers, viewsets
from rest_framework.request import Request
from rest_framework.response import Response


# Create your views here.
class ChatHistoryView(viewsets.ModelViewSet):
    queryset = ChatHistory.objects.all()

    def get_permissions(self) -> list[Any]:

        return [IsOwnerOrSharedUser()]

    def get_queryset(self) -> QuerySet:
        queryset = ChatHistory.objects.all()
        queryset: BaseManager[ChatHistory] = queryset.order_by("-created_at")
        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        if self.action in ["list"]:
            return ChatHistoryListSerializer
        elif self.action in ["create"]:
            return ChatHistoryRequestSerializer
        return ChatHistorySerializer

    def retrieve(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:

        chat_history = self.get_object()
        self.check_object_permissions(request, chat_history.app_deployment)

        serialized_instances = ChatTranscriptSerializer(
            chat_history.chat_history_transcript.all(), many=True
        ).data

        return Response(serialized_instances)

    def create(
        self,
        request: Request,
        *args: tuple[Any],
        **kwargs: dict[str, Any],
    ) -> Response:
        context = super().get_serializer_context()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app_id = serializer.validated_data.get("app_id")
        app_deployment = AppDeployment.objects.get(app_name=app_id)
        self.check_object_permissions(request, app_deployment)
        label = serializer.validated_data.get("label")

        serializer = ChatHistorySerializer(
            data={"label": label, "app_deployment": app_deployment.id}, context=context
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(serializer.data)
