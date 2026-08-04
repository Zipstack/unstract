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


def send_resource_shared(
    *,
    organization: Organization,
    group_ids: Iterable[int],
    actor_id: int,
    resource_kind: str,
    resource_id: str,
    share_action: str = ShareAction.SHARED.value,
) -> None:
    """Mail every current member of each group whose resource access changed.

    One email per group, so ``group_name`` in the template is always the group
    the recipient actually belongs to. ``share_action`` picks the wording.
    """
    service = _service()
    if service is None:
        return
    actor = _get_user(actor_id)
    resource, resource_name, resource_type = _load_resource(
        organization, resource_kind, resource_id
    )
    if actor is None or resource_type is None:
        logger.info(
            "group-notification: skipping resource share for %s/%s "
            "(actor_found=%s resource_type=%s)",
            resource_kind,
            resource_id,
            actor is not None,
            resource_type,
        )
        return
    for group in _groups_in_org(organization, group_ids):
        recipients = _live_member_users(
            organization, group.memberships.values_list("user_id", flat=True)
        )
        logger.info(
            "group-notification: task=%s group_id=%s action=%s recipient_count=%d",
            "notify_resource_shared_with_group",
            group.pk,
            share_action,
            len(recipients),
        )
        if not recipients:
            continue
        service.send_group_resource_shared_notification(
            resource_type=resource_type,
            resource_name=resource_name,
            resource_id=str(resource.pk),
            group_name=group.name,
            shared_by=actor,
            shared_to=recipients,
            resource_instance=resource,
            share_action=ShareAction(share_action).value,
        )


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
    actor = _get_user(actor_id)
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


def _get_user(user_id: int) -> User | None:
    return User.objects.filter(pk=user_id).first()


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
    memberships = OrganizationMember.objects.filter(
        organization=organization, user_id__in=list(user_ids)
    ).select_related("user")
    return [
        m.user
        for m in memberships
        if not getattr(m.user, "is_service_account", False) and m.user.email
    ]


def _load_resource(
    organization: Organization, kind: str, resource_id: str
) -> tuple[Any, str, str | None]:
    """Resolve the shared resource to ``(instance, display name, plugin type)``.

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
    return resource, name, _resource_type_for(descriptor, resource)


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
