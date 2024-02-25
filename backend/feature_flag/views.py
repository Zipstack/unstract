"""
    Feature Flag view file
Returns:
    evaluate response
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from unstract.flags.client import EvaluationClient

logger = logging.getLogger(__name__)


@api_view(["POST"])
def evaluate_feature_flag(request: Request) -> Response:
    """Function to evaluate the feature flag.

    To-Do: Refactor to a class based view, use serializers (DRF).

    Args:
        request: request object

    Returns:
        evaluate response
    """
    try:
        namespace_key = request.data.get("namespace_key")
        flag_key = request.data.get("flag_key")
        entity_id = request.data.get("entity_id")
        context = request.data.get("context")

        if not namespace_key or not flag_key or not entity_id:
            return Response(
                {"message": "Request paramteres are missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        evaluation_client = EvaluationClient()
        response = evaluation_client.boolean_evaluate_feature_flag(
            namespace_key=namespace_key,
            flag_key=flag_key,
            entity_id=entity_id,
            context=context,
        )

        return Response({"enabled": response}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("No response from server: %s", e)
        return Response(
            {"message": "No response from server"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
