from typing import Any, Optional

from apps.canned_question.exceptions import CannedQuestionBadRequestException
from apps.canned_question.models import CannedQuestion
from apps.canned_question.serializers import (
    CannedQuestionListSerializer,
    CannedQuestionResponseSerializer,
    CannedQuestionSerializer,
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

    def get_queryset(self) -> QuerySet:
        """Adding additional filters and default sorting.

        Returns:
            QuerySet: _description_
        """

        filter_args = FilterHelper.build_filter_args(
            self.request, RequestKey.IS_ACTIVE, RequestKey.APP_DEPLOYMENT
        )
        queryset = (
            CannedQuestion.objects.filter(**filter_args)
            if filter_args
            else CannedQuestion.objects.all()
        )

        order_by = self.request.query_params.get("order_by")
        if order_by == "desc":
            queryset = queryset.order_by("-modified_at")
        elif order_by == "asc":
            queryset = queryset.order_by("modified_at")

        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        if self.action in ["list"]:
            return CannedQuestionListSerializer
        return CannedQuestionSerializer

    @action(detail=True, methods=["get"])
    def fetch_one(self, request: Request, pk: Optional[str] = None) -> Response:
        """Custom action to fetch a single instance."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

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
        serializer: Serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            raise CannedQuestionBadRequestException(
                get_error_from_serializer(serializer.errors)
            )
        self.perform_create(serializer)

        response_serializer = CannedQuestionResponseSerializer(
            {**serializer.data}
        )

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
