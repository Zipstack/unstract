from typing import Any, Optional
from uuid import UUID

from apps.chat_history.models import ChatHistory
from apps.chat_transcript.chat_engine import ChatEngine
from apps.chat_transcript.models import ChatTranscript
from apps.chat_transcript.serializer import (
    ChatTranscriptListSerializer,
    ChatTranscriptSerializer,
)
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404
from llama_index.llms.types import MessageRole
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer

from backend.constants import RequestKey


# Create your views here.
class ChatTranscriptView(viewsets.ModelViewSet):
    queryset = ChatTranscript.objects.all()

    def get_queryset(self) -> QuerySet:
        # Extract chat_history_id from the URL
        filter_args = {
            RequestKey.CREATED_BY: self.request.user.id,
            RequestKey.CHAT_HISTORY: self.kwargs.get("chat_history_id"),
        }
        queryset = ChatTranscript.objects.filter(**filter_args)
        queryset = queryset.order_by("-created_at")
        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        if self.action in ["list"]:
            return ChatTranscriptListSerializer
        return ChatTranscriptSerializer

    @action(detail=True, methods=["get"])
    def fetch_one(
        self, request: Request, chat_history_id: Optional[str] = None
    ) -> Response:
        """Custom action to fetch a single instance."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(
        self,
        request: Request,
        chat_history_id: UUID,
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
        chat_history = get_object_or_404(ChatHistory, id=chat_history_id)
        serializer: Serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_message = serializer.save(
            chat_history=chat_history,
            role=MessageRole.USER,
        )

        chat_engine = ChatEngine(app_deployment=chat_history.app_deployment)
        assistant_message_data = {"message": chat_engine.chat(user_message.message)}
        assistant_message_serializer = self.get_serializer(data=assistant_message_data)
        assistant_message_serializer.is_valid()
        assistant_message = assistant_message_serializer.save(
            chat_history=chat_history,
            role=MessageRole.ASSISTANT,
            parent_message=user_message,
        )

        response_data = [
            ChatTranscriptListSerializer(user_message).data,
            ChatTranscriptListSerializer(assistant_message).data,
        ]

        return Response(data=response_data, status=status.HTTP_201_CREATED)


def get_error_from_serializer(error_details: dict[str, Any]) -> Optional[str]:
    """Method to return first error message.

    Args:
        error_details (dict[str, Any]): _description_

    Returns:
        Optional[str]: _description_
    """
    error_key = next(iter(error_details))
    # Get the first error message
    error_message: str = f"{error_details[error_key][0]} : {error_key}"
    return error_message
