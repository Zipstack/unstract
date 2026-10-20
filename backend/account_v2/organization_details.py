"""Role, member count and region for each organization in a user's list.

The list comes from the auth service, which can name organizations this
deployment has no data for: in cloud, regions share one identity provider. A
field is added only where this deployment can answer it, and is otherwise left
out of the row rather than sent as null:

- ``role``: the caller has a membership row in that organization here.
- ``member_count``: the organization exists here. Counts members who have
  signed in here, not pending invitations.
- ``region``: the organization exists here and ``settings.REGION`` is set.
"""

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from django.conf import settings
from django.db.models import Count
from tenant_account_v2.models import OrganizationMember

from account_v2.models import Organization, User


def with_member_details(organizations: Sequence[Any], user: User) -> list[dict[str, Any]]:
    """Return each organization as a dict with the details this deployment has.

    Args:
        organizations: dataclasses with an ``id`` holding the organization_id,
            in the order the list should keep.
        user: the user the list belongs to.

    Returns:
        New dicts in input order; the inputs are not changed.
    """
    ids = [org.id for org in organizations]
    member_counts = dict(
        Organization.objects.filter(organization_id__in=ids)
        .annotate(member_count=Count("organizationmember"))
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
        row = asdict(org)
        if org.id in roles:
            row["role"] = roles[org.id]
        if org.id in member_counts:
            row["member_count"] = member_counts[org.id]
            if region:
                row["region"] = region
        rows.append(row)
    return rows
