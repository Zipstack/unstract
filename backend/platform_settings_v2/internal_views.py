"""Internal API views for platform settings

Provides internal endpoints for workers to access platform settings
without direct database access.
"""

import logging

from account_v2.models import PlatformKey
from account_v2.organization import OrganizationService
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_settings_v2.platform_auth_service import PlatformAuthenticationService

logger = logging.getLogger(__name__)


class InternalPlatformKeyView(APIView):
    """Internal API to get active platform key for an organization."""

    def get(self, request):
        """Get active platform key for organization.

        Uses X-Organization-ID header to identify the organization.

        Args:
            request: HTTP request with X-Organization-ID header

        Returns:
            Response with platform key
        """
        try:
            # Get organization ID from header
            org_id = request.headers.get("X-Organization-ID")
            if not org_id:
                return Response(
                    {"error": "X-Organization-ID header is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get organization
            organization = OrganizationService.get_organization_by_org_id(org_id=org_id)

            if not organization:
                return Response(
                    {"error": f"Organization {org_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get active platform key
            platform_key = PlatformAuthenticationService.get_active_platform_key(
                organization_id=org_id
            )

            return Response(
                {
                    "platform_key": str(platform_key.key),
                    "key_name": platform_key.key_name,
                    "organization_id": org_id,
                },
                status=status.HTTP_200_OK,
            )

        except PlatformKey.DoesNotExist:
            return Response(
                {"error": f"No active platform key found for organization {org_id}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Error getting platform key for org {org_id}: {str(e)}")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
