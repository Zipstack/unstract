"""Account Internal API Views
Handles organization context related endpoints for internal services.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.organization_utils import get_organization_context, resolve_organization

from .internal_serializers import OrganizationContextSerializer

logger = logging.getLogger(__name__)


class OrganizationContextAPIView(APIView):
    """Internal API endpoint for getting organization context."""

    def get(self, request, org_id):
        """Get organization context information."""
        try:
            # Use shared utility to resolve organization
            organization = resolve_organization(org_id, raise_on_not_found=True)

            # Use shared utility to get context data
            context_data = get_organization_context(organization)

            serializer = OrganizationContextSerializer(context_data)

            logger.info(f"Retrieved organization context for {org_id}")

            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Failed to get organization context for {org_id}: {str(e)}")
            return Response(
                {"error": "Failed to get organization context", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
