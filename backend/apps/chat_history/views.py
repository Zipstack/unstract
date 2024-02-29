from typing import Any, Optional

from apps.chat_history.exceptions import ChatHistoryBadRequestException
from apps.chat_history.models import ChatHistory
from apps.chat_history.serializer import (
    ChatHistoryListSerializer,
    ChatHistoryResponseSerializer,
    ChatHistorySerializer,
)
from django.db.models.query import QuerySet
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from backend.constants import RequestKey
from utils.filtering import FilterHelper


# Create your views here.
class ChatHistoryView(viewsets.ModelViewSet):
    queryset = ChatHistory.objects.all()

    def get_queryset(self) -> QuerySet:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.APP_DEPLOYMENT,
        )
        filter_args.update({RequestKey.CREATED_BY: self.request.user.id})
        queryset = (
            ChatHistory.objects.filter(**filter_args)
            if filter_args
            else ChatHistory.objects.all()
        )
        queryset = queryset.order_by("-created_at")
        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        if self.action in ["list"]:
            return ChatHistoryListSerializer
        return ChatHistorySerializer

    @action(detail=True, methods=["get"])
    def fetch_one(self, request: Request, pk: Optional[str] = None) -> Response:
        """Custom action to fetch a single instance."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        """Method to create entry in Chat history.

        Args:
            request (Request): _description_

        Raises:
            ChatHistoryBadRequestException: _description_

        Returns:
            Response: _description_
        """
        serializer: Serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            raise ChatHistoryBadRequestException(
                get_error_from_serializer(serializer.errors)
            )
        self.perform_create(serializer)

        response_serializer = ChatHistoryResponseSerializer({**serializer.data})

        headers = self.get_success_headers(serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


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
