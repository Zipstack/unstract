"""Organization utilities for internal APIs.
Provides shared functions for organization context resolution.
"""

import logging
from typing import Any

from account_v2.models import Organization
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)


def resolve_organization(
    org_id: str, raise_on_not_found: bool = False
) -> Organization | None:
    """Resolve organization by either organization.id (int) or organization.organization_id (string).

    Args:
        org_id: Organization identifier - can be either the primary key (numeric string)
               or the organization_id field (string)
        raise_on_not_found: If True, raises Http404 on not found. If False, returns None.

    Returns:
        Organization instance if found, None if not found and raise_on_not_found=False

    Raises:
        Http404: If organization not found and raise_on_not_found=True
    """
    try:
        if org_id.isdigit():
            # If it's numeric, treat as primary key
            if raise_on_not_found:
                return get_object_or_404(Organization, id=org_id)
            else:
                return Organization.objects.get(id=org_id)
        else:
            # If it's string, treat as organization_id field
            if raise_on_not_found:
                return get_object_or_404(Organization, organization_id=org_id)
            else:
                return Organization.objects.get(organization_id=org_id)
    except Organization.DoesNotExist:
        if raise_on_not_found:
            raise
        logger.warning(f"Organization {org_id} not found")
        return None


def get_organization_context(organization: Organization) -> dict[str, Any]:
    """Get standardized organization context data.

    Args:
        organization: Organization instance

    Returns:
        Dictionary with organization context information
    """
    return {
        "organization_id": str(organization.id),
        "organization_name": organization.display_name,
        "organization_slug": getattr(organization, "slug", ""),
        "created_at": organization.created_at.isoformat()
        if hasattr(organization, "created_at")
        else None,
        "settings": {
            # Add organization-specific settings here
            "subscription_active": True,  # This would come from subscription model
            "features_enabled": [],  # This would come from feature flags
        },
    }


def filter_queryset_by_organization(queryset, request, organization_field="organization"):
    """Filter a Django queryset by organization context from request.

    Args:
        queryset: Django QuerySet to filter
        request: HTTP request object with organization_id attribute
        organization_field: Field name for organization relationship (default: 'organization')

    Returns:
        Filtered queryset or empty queryset if organization not found
    """
    org_id = getattr(request, "organization_id", None)
    if org_id:
        organization = resolve_organization(org_id, raise_on_not_found=False)
        if organization:
            # Use dynamic field lookup
            filter_kwargs = {organization_field: organization}
            return queryset.filter(**filter_kwargs)
        else:
            # Return empty queryset if organization not found
            return queryset.none()
    return queryset
