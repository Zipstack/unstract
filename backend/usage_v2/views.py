import logging

from django.http import HttpRequest
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .constants import UsageKeys
from .helper import UsageHelper
from .serializers import GetUsageSerializer

logger = logging.getLogger(__name__)


class UsageView(viewsets.ModelViewSet):
    """Viewset for managing Usage-related operations."""

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
