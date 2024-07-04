from typing import Any

from django.db.models.query import QuerySet
from pluggable_apps.apps.app_deployment.multi_doc_service import MultiDocService
from pluggable_apps.apps.chat_transcript.enum import Roles
from pluggable_apps.apps.chat_transcript.models import ChatTranscript
from pluggable_apps.apps.chat_transcript.serializer import ChatTranscriptSerializer
from rest_framework import serializers, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_session import UserSessionUtils


# Create your views here.
class ChatTranscriptView(viewsets.ModelViewSet):
    queryset = ChatTranscript.objects.all()

    def get_queryset(self) -> QuerySet:
        return ChatTranscript.objects.all()

    def get_serializer_class(self) -> serializers.ModelSerializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        return ChatTranscriptSerializer

    def create(
        self,
        request: Request,
        *args: tuple[Any],
        **kwargs: dict[str, Any],
    ) -> Response:
        """Method to create entry in Chat Transcript.

        Args:
            request (Request): _description_

        Raises:
            ChatTranscriptBadRequestException: _description_

        Returns:
            Response: _description_
        """
        context = super().get_serializer_context()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)
        chat_history = serializer.validated_data.get("chat_history")
        app_name = chat_history.app_deployment.app_name
        message = serializer.validated_data.get("message")
        # # Call Chat API
        org_id = UserSessionUtils.get_organization_id(request)
        multi_doc_service = MultiDocService(org_id=org_id, email=request.user.email)

        chat_response = multi_doc_service.chat(question=message, tag=app_name)

        chat_response_serializer = ChatTranscriptSerializer(
            data={
                "message": chat_response["response"],
                "chat_history": chat_history.id,
                "role": Roles.ASSISTANT.value,
            },
            context=context,
        )
        chat_response_serializer.is_valid(raise_exception=True)
        self.perform_create(chat_response_serializer)
        chat_history.session_id = chat_response["session_id"]
        chat_history.save()

        return Response(
            chat_response_serializer.data,
        )
