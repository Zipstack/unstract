import logging

from django.http import HttpRequest
from django_filters.rest_framework import DjangoFilterBackend
from permissions.permission import IsOrganizationMember
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.date import DateTimeProcessor
from utils.pagination import CustomPagination
from utils.user_context import UserContext

from usage_v2.filter import UsageFilter

from .constants import UsageKeys
from .helper import UsageHelper
from .models import Usage
from .serializers import GetUsageSerializer, UsageSerializer

logger = logging.getLogger(__name__)


class UsageView(viewsets.ModelViewSet):
    """Viewset for managing Usage-related operations."""

    permission_classes = [IsAuthenticated, IsOrganizationMember]
    serializer_class = UsageSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = UsageFilter
    ordering_fields = ["created_at"]

    def get_queryset(self):
        """Returns a queryset filtered by the current user's organization."""
        user_organization = UserContext.get_organization()
        queryset = Usage.objects.filter(organization=user_organization)
        return queryset

    @action(detail=True, methods=["get"], url_path="aggregate")
    def aggregate(self, request: HttpRequest) -> Response:
        """Custom action to list Usage data for a given Tag, grouped by
        WorkflowFileExecution.
        """
        date_range = DateTimeProcessor.process_date_range(
            start_date_param=request.query_params.get("created_at_gte"),
            end_date_param=request.query_params.get("created_at_lte"),
        )
        date_range_param = request.query_params.get("date_range")
        if date_range_param:
            date_range = DateTimeProcessor.filter_date_range(date_range_param)
        # Get filtered queryset
        queryset = self.filter_queryset(self.get_queryset()).filter(
            created_at__range=[date_range.start_date, date_range.end_date]
        )

        # Aggregate and prepare response
        aggregated_data = UsageHelper.aggregate_usage_metrics(queryset)
        response_data = UsageHelper.format_usage_response(
            aggregated_data, date_range.start_date, date_range.end_date
        )

        return Response(status=status.HTTP_200_OK, data=response_data)

    @action(detail=True, methods=["get"])
    def get_token_usage(self, request: HttpRequest) -> Response:
        """Retrieves the aggregated token usage for a given run_id.

        This method validates the 'run_id' query parameter, aggregates the token
        usage statistics for the specified run_id, and returns the results.

        Args:
            request (HttpRequest): The HTTP request object containing the
            query parameters.

        Returns:
            Response: A Response object containing the aggregated token usage data
                      with HTTP 200 OK status if successful, or an error message and
                      appropriate HTTP status if an error occurs.
        """
        # Validate the query parameters using the serializer
        # This ensures that 'run_id' is present and valid
        serializer = GetUsageSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        run_id = serializer.validated_data.get(UsageKeys.RUN_ID)

        # Retrieve aggregated token count for the given run_id.
        result: dict = UsageHelper.get_aggregated_token_count(run_id=run_id)

        # Log the successful completion of the operation
        logger.info(f"Token usage retrieved successfully for run_id: {run_id}")

        # Return the result
        return Response(status=status.HTTP_200_OK, data=result)
