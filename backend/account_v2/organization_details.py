"""Role, member count and region for each organization in a user's list.

The list comes from the auth service, which can name organizations this
deployment has no data for: in cloud, regions share one identity provider. A
field is added only where this deployment can answer it, and is otherwise left
out of the row rather than sent as null:

- ``role``: the caller has a membership row in that organization here.
- ``member_count``: the organization exists here. Counts the people the
  members page lists: the organization's member records here, without
  platform API key accounts. Pending invitations have no record yet.
- ``region``: the organization exists here and ``settings.REGION`` is set.
"""

from collections.abc import Sequence
from typing import Any, Protocol

from django.conf import settings
from django.db.models import Count, Q
from tenant_account_v2.models import OrganizationMember

from account_v2.models import Organization, User


class ListedOrganization(Protocol):
    """What the auth services return for each organization.

    ``metadata`` is read too where the object has it (cloud does, OSS
    doesn't); a Protocol can't declare an optional attribute.
    """

    id: str
    display_name: str
    name: str


def with_member_details(
    organizations: Sequence[ListedOrganization], user: User
) -> list[dict[str, Any]]:
    """Return each organization as a dict with the details this deployment has.

    Args:
        organizations: objects with ``id`` (the organization_id),
            ``display_name``, ``name`` and optionally ``metadata``, in the
            order the list should keep.
        user: the user the list belongs to.

    Returns:
        New dicts in input order; the inputs are not changed.
    """
    ids = [org.id for org in organizations]
    member_counts = dict(
        Organization.objects.filter(organization_id__in=ids)
        .annotate(
            # Same rule as OrganizationMemberService.get_members (the members
            # page): platform API key accounts are members but not people.
            member_count=Count(
                "organizationmember",
                filter=Q(organizationmember__user__is_service_account=False),
            )
        )
        .values_list("organization_id", "member_count")
    )
    # _base_manager: the default manager filters to the request's organization.
    roles = dict(
        OrganizationMember._base_manager.filter(
            user=user, organization__organization_id__in=ids
        ).values_list("organization__organization_id", "role")
    )
    region = getattr(settings, "REGION", None)

    rows = []
    for org in organizations:
        row: dict[str, Any] = {
            "id": org.id,
            "display_name": org.display_name,
            "name": org.name,
            "metadata": getattr(org, "metadata", None),
        }
        if org.id in roles:
            row["role"] = roles[org.id]
        if org.id in member_counts:
            row["member_count"] = member_counts[org.id]
            if region:
                row["region"] = region
        rows.append(row)
    return rows
