"""Internal API views for Configuration access by workers."""

import logging

from account_v2.models import Organization
from django.http import JsonResponse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView

from .models import Configuration

logger = logging.getLogger(__name__)


class ConfigurationInternalView(APIView):
    """Internal API view for workers to access organization configurations.

    This endpoint allows workers to get organization-specific configuration
    values without direct database access, maintaining the same logic as
    Configuration.get_value_by_organization() but over HTTP.

    Workers can call this to get configs like MAX_PARALLEL_FILE_BATCHES
    with proper organization-specific overrides and fallbacks.
    """

    def get(self, request: Request, config_key: str) -> JsonResponse:
        """Get configuration value for an organization.

        Args:
            request: HTTP request with organization_id parameter
            config_key: Configuration key name (e.g., "MAX_PARALLEL_FILE_BATCHES")

        Returns:
            JSON response with configuration value and metadata
        """
        try:
            organization_id = request.query_params.get("organization_id")

            if not organization_id:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "organization_id parameter is required",
                        "config_key": config_key,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the organization - handle both ID (int) and organization_id (string)
            try:
                # Try to get organization by primary key ID first (for backward compatibility)
                if organization_id.isdigit():
                    organization = Organization.objects.get(id=int(organization_id))
                else:
                    # Otherwise, lookup by organization_id field (string identifier)
                    organization = Organization.objects.get(
                        organization_id=organization_id
                    )
            except (Organization.DoesNotExist, ValueError):
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Organization {organization_id} not found",
                        "config_key": config_key,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get the configuration value using the same logic as the backend
            try:
                config_value = Configuration.get_value_by_organization(
                    config_key=config_key, organization=organization
                )

                # Check if we found an organization-specific override
                has_override = False
                try:
                    Configuration.objects.get(
                        organization=organization, key=config_key, enabled=True
                    )
                    has_override = True
                except Configuration.DoesNotExist:
                    has_override = False

                return JsonResponse(
                    {
                        "success": True,
                        "data": {
                            "config_key": config_key,
                            "value": config_value,
                            "organization_id": organization_id,
                            "has_organization_override": has_override,
                        },
                    }
                )

            except ValueError as e:
                # Configuration key not found in registry
                return JsonResponse(
                    {
                        "success": False,
                        "error": str(e),
                        "config_key": config_key,
                        "organization_id": organization_id,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except Exception as e:
            logger.error(
                f"Error getting configuration {config_key} for organization {organization_id}: {e}",
                exc_info=True,
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "Internal server error",
                    "config_key": config_key,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
