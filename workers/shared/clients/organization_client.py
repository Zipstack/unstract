"""Organization API Client for Organization Context Management

This module provides specialized API client for organization-related operations,
extracted from the monolithic InternalAPIClient to improve maintainability.

Handles:
- Organization context management
- Organization-specific API calls
- Multi-tenant organization scoping
- Organization permissions and access control
"""

import logging

from unstract.core.data_models import OrganizationContext

from ..data_models import APIResponse
from ..retry_utils import circuit_breaker
from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class OrganizationAPIClient(BaseAPIClient):
    """Specialized API client for organization context management.

    This client handles all organization-related operations including:
    - Getting organization context and metadata
    - Setting organization context for API calls
    - Managing organization-scoped permissions
    - Organization membership management
    - Multi-tenant organization operations
    """

    def get_organization_context(self, org_id: str) -> OrganizationContext:
        """Get organization context and metadata.

        Args:
            org_id: Organization ID

        Returns:
            Organization context data including permissions, settings, and metadata
        """
        logger.debug(f"Getting organization context for {org_id}")

        try:
            response = self.get(self._build_url("organization", f"{org_id}/context/"))

            org_name = response.get("name", "Unknown")
            logger.debug(f"Retrieved organization context for {org_name} ({org_id})")

            return OrganizationContext(
                organization_id=org_id,
                tenant_id=response.get("tenant_id"),
                subscription_plan=response.get("subscription_plan"),
            )

        except Exception as e:
            logger.error(f"Failed to get organization context for {org_id}: {str(e)}")
            raise

    def get_organization_details(self, org_id: str) -> APIResponse:
        """Get detailed organization information.

        Args:
            org_id: Organization ID

        Returns:
            Detailed organization information
        """
        logger.debug(f"Getting organization details for {org_id}")

        try:
            response = self.get(self._build_url("organization", f"{org_id}/"))

            org_name = response.get("name", "Unknown")
            logger.debug(f"Retrieved organization details for {org_name} ({org_id})")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization details for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_organization_settings(self, org_id: str) -> APIResponse:
        """Get organization-specific settings and configuration.

        Args:
            org_id: Organization ID

        Returns:
            Organization settings and configuration
        """
        logger.debug(f"Getting organization settings for {org_id}")

        try:
            response = self.get(self._build_url("organization", f"{org_id}/settings/"))

            logger.debug(f"Retrieved organization settings for {org_id}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization settings for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_organization_permissions(
        self, org_id: str, user_id: str | None = None
    ) -> APIResponse:
        """Get organization permissions for a user or current context.

        Args:
            org_id: Organization ID
            user_id: Optional user ID (defaults to current user)

        Returns:
            Organization permissions data
        """
        params = {}
        if user_id:
            params["user_id"] = user_id

        logger.debug(f"Getting organization permissions for {org_id}")

        try:
            response = self.get(
                self._build_url("organization", f"{org_id}/permissions/"), params=params
            )

            logger.debug(f"Retrieved organization permissions for {org_id}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization permissions for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_organization_members(
        self, org_id: str, active_only: bool = True
    ) -> APIResponse:
        """Get organization members list.

        Args:
            org_id: Organization ID
            active_only: Whether to return only active members

        Returns:
            Organization members data
        """
        params = {"active_only": active_only}

        logger.debug(f"Getting organization members for {org_id}")

        try:
            response = self.get(
                self._build_url("organization", f"{org_id}/members/"), params=params
            )

            member_count = len(response.get("members", []))
            logger.debug(f"Retrieved {member_count} organization members for {org_id}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization members for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_organization_usage(self, org_id: str, period: str = "month") -> APIResponse:
        """Get organization usage statistics.

        Args:
            org_id: Organization ID
            period: Usage period (day, week, month, year)

        Returns:
            Organization usage statistics
        """
        params = {"period": period}

        logger.debug(f"Getting organization usage for {org_id} (period: {period})")

        try:
            response = self.get(
                self._build_url("organization", f"{org_id}/usage/"), params=params
            )

            logger.debug(f"Retrieved organization usage for {org_id}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization usage for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_organization_quota(self, org_id: str) -> APIResponse:
        """Get organization resource quotas and limits.

        Args:
            org_id: Organization ID

        Returns:
            Organization quota information
        """
        logger.debug(f"Getting organization quota for {org_id}")

        try:
            response = self.get(self._build_url("organization", f"{org_id}/quota/"))

            logger.debug(f"Retrieved organization quota for {org_id}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization quota for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def validate_organization_access(
        self, org_id: str, resource_type: str, action: str
    ) -> APIResponse:
        """Validate organization access for a specific resource and action.

        Args:
            org_id: Organization ID
            resource_type: Type of resource (workflow, file, etc.)
            action: Action to validate (read, write, execute, etc.)

        Returns:
            Access validation result
        """
        data = {"resource_type": resource_type, "action": action}

        logger.debug(
            f"Validating organization access for {org_id}: {resource_type}.{action}"
        )

        try:
            response = self.post(
                self._build_url("organization", f"{org_id}/validate-access/"), data
            )

            is_allowed = response.get("allowed", False)
            logger.debug(f"Organization access validation for {org_id}: {is_allowed}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to validate organization access for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    @circuit_breaker(failure_threshold=3, recovery_timeout=60.0)
    def get_organization_health(self, org_id: str) -> APIResponse:
        """Get organization health status and service availability.

        Args:
            org_id: Organization ID

        Returns:
            Organization health status
        """
        logger.debug(f"Getting organization health for {org_id}")

        try:
            response = self.get(self._build_url("organization", f"{org_id}/health/"))

            status = response.get("status", "unknown")
            logger.debug(f"Organization health for {org_id}: {status}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization health for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def switch_organization_context(self, org_id: str) -> APIResponse:
        """Switch to a different organization context.

        This method validates the organization access and switches the client context
        to the specified organization for subsequent API calls.

        Args:
            org_id: Organization ID to switch to

        Returns:
            Organization context switch result
        """
        logger.info(f"Switching organization context to {org_id}")

        try:
            # Validate organization access first
            context = self.get_organization_context(org_id)

            # If successful, update the client's organization context
            self.set_organization_context(org_id)

            logger.info(f"Successfully switched organization context to {org_id}")
            return APIResponse(
                success=True,
                data={"organization_id": org_id, "context": context.to_dict()},
                status_code=200,
            )

        except Exception as e:
            logger.error(f"Failed to switch organization context to {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_organization_workflows(
        self, org_id: str, workflow_type: str | None = None
    ) -> APIResponse:
        """Get workflows for a specific organization.

        Args:
            org_id: Organization ID
            workflow_type: Optional workflow type filter

        Returns:
            Organization workflows
        """
        params = {}
        if workflow_type:
            params["workflow_type"] = workflow_type

        logger.debug(f"Getting organization workflows for {org_id}")

        try:
            response = self.get(
                self._build_url("organization", f"{org_id}/workflows/"), params=params
            )

            workflow_count = len(response.get("workflows", []))
            logger.debug(
                f"Retrieved {workflow_count} workflows for organization {org_id}"
            )
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization workflows for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_organization_connectors(
        self, org_id: str, connector_type: str | None = None
    ) -> APIResponse:
        """Get connectors for a specific organization.

        Args:
            org_id: Organization ID
            connector_type: Optional connector type filter

        Returns:
            Organization connectors
        """
        params = {}
        if connector_type:
            params["connector_type"] = connector_type

        logger.debug(f"Getting organization connectors for {org_id}")

        try:
            response = self.get(
                self._build_url("organization", f"{org_id}/connectors/"), params=params
            )

            connector_count = len(response.get("connectors", []))
            logger.debug(
                f"Retrieved {connector_count} connectors for organization {org_id}"
            )
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get organization connectors for {org_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))
