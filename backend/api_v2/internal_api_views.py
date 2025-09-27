"""Internal API Views for API v2

This module provides internal API endpoints for worker communication,
specifically optimized for type-aware pipeline data fetching.

Since we know the context from worker function calls:
- process_batch_callback_api -> APIDeployment model
- process_batch_callback -> Pipeline model (handled in workflow_manager)

This provides direct access to APIDeployment model data without
the overhead of checking both Pipeline and APIDeployment models.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_v2.models import APIDeployment
from api_v2.serializers import APIDeploymentSerializer

logger = logging.getLogger(__name__)


class APIDeploymentDataView(APIView):
    """Internal API endpoint for fetching APIDeployment data.

    This endpoint is optimized for callback workers that know they're dealing
    with API deployments. It directly queries the APIDeployment model without
    checking the Pipeline model, improving performance.

    Endpoint: GET /v2/api-deployments/{api_id}/data/
    """

    def get(self, request, api_id):
        """Get APIDeployment model data by API ID.

        Args:
            request: HTTP request object
            api_id: APIDeployment UUID

        Returns:
            Response with APIDeployment model data
        """
        try:
            logger.debug(f"Fetching APIDeployment data for ID: {api_id}")

            # Query APIDeployment model directly (organization-scoped via DefaultOrganizationMixin)
            api_deployment = APIDeployment.objects.get(id=api_id)

            # Serialize the APIDeployment model
            serializer = APIDeploymentSerializer(api_deployment)

            # Use consistent response format with pipeline endpoint
            response_data = {"status": "success", "pipeline": serializer.data}

            logger.info(
                f"Found APIDeployment {api_id}: name='{api_deployment.api_name}', display_name='{api_deployment.display_name}'"
            )
            return Response(response_data, status=status.HTTP_200_OK)

        except APIDeployment.DoesNotExist:
            logger.warning(f"APIDeployment not found for ID: {api_id}")
            return Response(
                {"error": f"APIDeployment with ID {api_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Error fetching APIDeployment data for {api_id}: {str(e)}")
            return Response(
                {"error": f"Failed to fetch APIDeployment data: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
