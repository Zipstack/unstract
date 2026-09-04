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
    """Filter a Django queryset by the request's organization context.

    Fails closed. For every caller, this function is the only tenant boundary
    in the request: each one reaches it with ``OrganizationFilterBackend``
    inert, either by opting out with ``skip_org_filter = True`` or by being on
    a view class that declares no filter backends at all. Returning the
    queryset unfiltered when there is no organization context would hand back
    every organization's rows.

    Scope note: ``OrgAwareManager`` draws the same line, on the same
    condition. It fails closed whenever an organization identifier is set but
    does not resolve, and stays open only when no identifier is set at all —
    Celery tasks, management commands and the shell, which have no request to
    take one from. Callers overlap: the ``@csrf_exempt`` internal views reach
    both. Fail-open there is the absence of a request, not the absence of a
    header.

    The absent-header case is not exotic: ``InternalAPIAuthMiddleware`` logs a
    warning and continues when ``X-Organization-ID`` is missing, so any caller
    holding the internal service key reaches here without context simply by
    omitting it.

    Note for callers that genuinely span organizations — the leader-elected
    reaper is one — query the model directly rather than routing through here.
    ``recover_stuck_pg_executions`` already does, which is why failing closed
    does not affect it.

    Args:
        queryset: Django QuerySet to filter
        request: HTTP request object with organization_id attribute
        organization_field: Field name for organization relationship (default: 'organization')

    Returns:
        The queryset filtered to the request's organization, or an empty
        queryset when the organization is absent or unresolvable.
    """
    org_id = getattr(request, "organization_id", None)
    if not org_id:
        logger.warning(
            "Organization scoping requested without organization context on %s; "
            "returning no rows. A caller that must span organizations should "
            "query the model directly instead of using this helper.",
            getattr(request, "path", "<unknown path>"),
        )
        return queryset.none()

    organization = resolve_organization(org_id, raise_on_not_found=False)
    if not organization:
        logger.warning("Organization %s not found; returning no rows.", org_id)
        return queryset.none()

    return queryset.filter(**{organization_field: organization})
