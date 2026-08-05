"""Send-side logic for group-sharing email notifications (UN-3494 / mfbt UNS-848).

Reached over the internal API by the notification worker. The enqueue side
(:mod:`tenant_account_v2.share_notifications`) only records *what happened*;
everything that needs Django — group expansion, org re-validation, resource
lookup, the email plugin — happens here, because ``workers/`` has no Django.

Sending is a cloud plugin. In OSS ``notification_plugin`` is empty and every
entry point below no-ops cleanly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from account_v2.models import Organization, User
from django.apps import apps
from django.db.models import QuerySet
from plugins import get_plugin

from tenant_account_v2.models import OrganizationGroup, OrganizationMember
from tenant_account_v2.share_notifications import MembershipAction, ShareAction
from tenant_account_v2.shareable_resources import ShareableResource, descriptor_for_kind

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

logger = logging.getLogger(__name__)

notification_plugin = get_plugin("notification")

# OSS ``ShareableResource.kind`` → the email plugin's ``ResourceType`` value.
# Deliberately plain strings: OSS must not import a cloud-only enum. Not a 1:1
# rename — pipelines and adapters resolve from the instance below.
_STATIC_RESOURCE_TYPES = {
    "workflow": "workflow",
    "api_deployment": "api",
    "connector_instance": "connector",
    "custom_tool": "text_extractor",
    "agentic_project": "agentic_project",
}
_ADAPTER_RESOURCE_TYPES = {
    "LLM": "llm",
    "EMBEDDING": "embedding",
    "VECTOR_DB": "vector_db",
    "X2TEXT": "x2text",
}
# Only ETL/TASK pipelines map to a notification resource type; the plugin
# compares against these exact (uppercase) values.
_PIPELINE_RESOURCE_TYPES = frozenset({"ETL", "TASK"})


class ResourceNotFoundError(Exception):
    """The shared resource no longer exists, or is not in the given org."""


@dataclass(frozen=True)
class _SharedResource:
    """A resolved resource, reused across every group email in one task."""

    instance: Any
    name: str
    type: str | None


def send_resource_shared(
    *,
    organization: Organization,
    group_ids: Iterable[int],
    actor_id: int,
    resource_kind: str,
    resource_id: str,
    share_action: str = ShareAction.SHARED.value,
    revoked_at: datetime | None = None,
) -> None:
    """Mail every current member of each group whose resource access changed.

    One email per group, so ``group_name`` in the template is always the group
    the recipient actually belongs to. ``share_action`` picks the wording, and
    on a revoke ``revoked_at`` bounds who counts as "current".
    """
    service = _service()
    if service is None:
        return
    actor = _get_user(organization, actor_id)
    shared = _load_resource(organization, resource_kind, resource_id)
    if actor is None or shared.type is None:
        logger.info(
            "group-notification: skipping resource share for %s/%s "
            "(actor_found=%s resource_type=%s)",
            resource_kind,
            resource_id,
            actor is not None,
            shared.type,
        )
        return
    retained = _retained_user_ids(shared.instance, share_action)
    for group in _groups_in_org(organization, group_ids):
        recipients = _group_recipients(organization, group, retained, revoked_at)
        logger.info(
            "group-notification: task=notify_resource_shared_with_group "
            "group_id=%s action=%s recipient_count=%d",
            group.pk,
            share_action,
            len(recipients),
        )
        if recipients:
            _mail_group(service, group, recipients, shared, actor, share_action)


def send_membership_changed(
    *,
    organization: Organization,
    group_id: int,
    actor_id: int,
    membership_action: str,
    user_ids: Iterable[int],
) -> None:
    """Mail the users whose membership of ``group_id`` just changed.

    Recipients are re-validated against ``OrganizationMember`` — this is where
    the offboarding race closes, for removals as well as additions: leaving a
    group does not remove someone from the org, so both directions validate the
    same way.
    """
    service = _service()
    if service is None:
        return
    actor = _get_user(organization, actor_id)
    group = _groups_in_org(organization, [group_id]).first()
    if actor is None or group is None:
        logger.info(
            "group-notification: skipping membership change for group %s "
            "(actor_found=%s group_found=%s)",
            group_id,
            actor is not None,
            group is not None,
        )
        return
    recipients = _live_member_users(organization, user_ids)
    logger.info(
        "group-notification: task=%s group_id=%s action=%s recipient_count=%d",
        "notify_group_membership_changed",
        group.pk,
        membership_action,
        len(recipients),
    )
    if not recipients:
        return
    service.send_group_membership_notification(
        group_name=group.name,
        membership_action=MembershipAction(membership_action).value,
        recipients=recipients,
        actor=actor,
        organization=organization,
    )


def _service() -> Any | None:
    """The cloud email service, or ``None`` when the plugin is absent (OSS)."""
    if not notification_plugin:
        logger.debug("group-notification: notification plugin unavailable, skipping")
        return None
    return notification_plugin["service_class"]()


def _get_user(organization: Organization, user_id: int) -> User | None:
    """The actor, re-validated against the org like every recipient is.

    Service accounts are kept: a share performed by a platform account must
    still notify the group.
    """
    member = (
        OrganizationMember.objects.filter(organization=organization, user_id=user_id)
        .select_related("user")
        .first()
    )
    return member.user if member else None


def _retained_user_ids(resource: Any, share_action: str) -> set[int]:
    """Users who still reach ``resource``; empty on the share direction.

    A revoked group's members may keep access through another group, a direct
    share or an org-wide share — telling them it was removed would be wrong,
    and the revoke email also repoints their CTA at the dashboard. Owners sit
    outside ``compute_effective_members`` by design, so add them back: an owner
    in the revoked group has lost nothing.
    """
    if share_action != ShareAction.REVOKED.value:
        return set()
    from tenant_account_v2.sharing_helpers import compute_effective_members

    return {member["user_id"] for member in compute_effective_members(resource)} | {
        owner.pk for owner in resource.owners()
    }


def _group_recipients(
    organization: Organization,
    group: OrganizationGroup,
    retained: set[int],
    joined_before: datetime | None = None,
) -> list[User]:
    """Live members of ``group`` who did not keep access via ``retained``.

    ``joined_before`` (a revoke's timestamp) drops anyone who joined after the
    access was taken away: they never held it through this group, so a
    revocation notice would be about access they never had.
    """
    memberships = group.memberships
    if joined_before is not None:
        memberships = memberships.filter(created_at__lte=joined_before)
    users = _live_member_users(
        organization, memberships.values_list("user_id", flat=True)
    )
    return [user for user in users if user.pk not in retained]


def _mail_group(
    service: Any,
    group: OrganizationGroup,
    recipients: list[User],
    shared: _SharedResource,
    actor: User,
    share_action: str,
) -> None:
    """Send one group's copy of the resource-share email."""
    service.send_group_resource_shared_notification(
        resource_type=shared.type,
        resource_name=shared.name,
        resource_id=str(shared.instance.pk),
        group_name=group.name,
        shared_by=actor,
        shared_to=recipients,
        resource_instance=shared.instance,
        share_action=ShareAction(share_action).value,
    )


def _groups_in_org(
    organization: Organization, group_ids: Iterable[int]
) -> QuerySet[OrganizationGroup]:
    """Groups from ``group_ids`` that belong to ``organization``."""
    return OrganizationGroup.objects.filter(
        organization=organization, pk__in=list(group_ids)
    )


def _live_member_users(organization: Organization, user_ids: Iterable[int]) -> list[User]:
    """Users from ``user_ids`` who are still live members of ``organization``.

    Service accounts are excluded, matching ``compute_effective_members``.
    """
    requested = list(user_ids)
    memberships = OrganizationMember.objects.filter(
        organization=organization, user_id__in=requested
    ).select_related("user")
    users = [
        m.user
        for m in memberships
        if not getattr(m.user, "is_service_account", False) and m.user.email
    ]
    if len(users) != len(requested):
        logger.info(
            "group-notification: dropped %d of %d recipients "
            "(left the org / service account / no email)",
            len(requested) - len(users),
            len(requested),
        )
    return users


def _load_resource(
    organization: Organization, kind: str, resource_id: str
) -> _SharedResource:
    """Resolve the shared resource for the email senders.

    Raises:
        ResourceNotFoundError: the descriptor, model, or row is missing — the
            resource was deleted or belongs to another org. Callers turn this
            into a success so the queue stops retrying.
    """
    descriptor = descriptor_for_kind(kind)
    if descriptor is None:
        raise ResourceNotFoundError(f"Unknown resource kind: {kind}")
    try:
        model = apps.get_model(descriptor.app_label, descriptor.model_name)
    except LookupError as exc:  # cloud-only app not installed here
        raise ResourceNotFoundError(f"Model unavailable for kind: {kind}") from exc
    # Filter on the organization explicitly rather than trusting the default
    # manager: ``AgenticProject``'s manager deliberately spans organizations.
    resource = model.objects.filter(
        organization=organization, **{descriptor.id_field: resource_id}
    ).first()
    if resource is None:
        raise ResourceNotFoundError(f"{kind} {resource_id} not found in organization")
    name = getattr(resource, descriptor.name_field, "") or ""
    return _SharedResource(resource, name, _resource_type_for(descriptor, resource))


def _resource_type_for(descriptor: ShareableResource, resource: Any) -> str | None:
    """Map a resource to the email plugin's ``ResourceType`` value.

    Returns ``None`` for resources the plugin has no type for (e.g. a pipeline
    that is neither ETL nor TASK) — the caller skips rather than guessing.
    """
    if descriptor.kind == "pipeline":
        pipeline_type = getattr(resource, "pipeline_type", None)
        return pipeline_type if pipeline_type in _PIPELINE_RESOURCE_TYPES else None
    if descriptor.kind == "adapter_instance":
        # Unknown adapter types fall back to ``llm``, matching the co-owner
        # path's override — an OCR adapter shared with a group should not
        # silently send nothing when sharing it with a co-owner mails fine.
        return _ADAPTER_RESOURCE_TYPES.get(str(resource.adapter_type or ""), "llm")
    return _STATIC_RESOURCE_TYPES.get(descriptor.kind)
