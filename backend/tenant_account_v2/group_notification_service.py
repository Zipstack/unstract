"""Send-side logic for group-sharing email notifications.

Reached over the internal API by the notification worker. The enqueue side
(:mod:`tenant_account_v2.share_notifications`) only records *what happened*;
everything that needs Django — group expansion, org re-validation, resource
lookup, the email plugin — happens here, because ``workers/`` has no Django.

Sending is a cloud plugin. In OSS ``notification_plugin`` is empty and every
entry point below no-ops cleanly.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from account_v2.models import Organization, User
from django.apps import apps
from django.conf import settings
from django.db.models import QuerySet
from plugins import get_plugin

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
)
from tenant_account_v2.notification_resource_types import (
    adapter_notification_type,
    pipeline_notification_type,
)
from tenant_account_v2.share_notifications import MembershipAction, ShareAction
from tenant_account_v2.shareable_resources import ShareableResource, descriptor_for_kind

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

logger = logging.getLogger(__name__)

notification_plugin = get_plugin("notification")

# Ceiling on concurrent per-group sends, mirroring the email plugin's own
# ``MAX_CONCURRENT_CHUNK_SENDS`` -- a resource shared with many groups would
# otherwise serialize one blocking SendGrid call per group.
_MAX_CONCURRENT_GROUP_SENDS = 10

# OSS ``ShareableResource.kind`` → the email plugin's ``ResourceType`` value,
# for the 6 kinds that are a plain 1:1 rename. Pipelines and adapters resolve
# via ``notification_resource_types`` instead, the same helpers the
# direct-share viewsets use, so a new adapter/pipeline type only needs
# registering once. These 6 are still a second, hand-maintained copy of what
# each ViewSet's own ``get_notification_resource_type`` already states --
# unifying them the same way is a larger change than this one, tracked
# separately. Plain strings here, not the cloud enum: this dict is only ever
# read once the plugin is confirmed loaded (see ``_service()``), but nothing
# enforces that path if a future caller reached it another way.
_STATIC_RESOURCE_TYPES = {
    "workflow": "workflow",
    "api_deployment": "api",
    "connector_instance": "connector",
    "custom_tool": "text_extractor",
    "agentic_project": "agentic_project",
    "lookup": "lookup",
}


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
    share_action: str,
    revoked_at: datetime | None = None,
) -> bool:
    """Mail every current member of each group whose resource access changed.

    One email per group, so ``group_name`` in the template is always the group
    the recipient actually belongs to. ``share_action`` picks the wording, and
    on a revoke ``revoked_at`` bounds who counts as "current".

    Returns:
        ``False`` only when a group with real recipients was actually attempted
        and the plugin reported a send failure -- the caller's cue to ask for
        redelivery. Every other outcome (nothing to send, plugin absent,
        misconfigured) is ``True``: there is nothing a retry would fix.
    """
    service = _service()
    if service is None:
        return True
    resolved = _resolve_share(organization, actor_id, resource_kind, resource_id)
    if resolved is None:
        return True
    actor, shared = resolved
    retained = _retained_user_ids(organization, shared.instance, share_action)
    if retained is None:
        return True
    groups = list(_groups_to_mail(organization, group_ids, shared.instance, share_action))
    recipients_by_group = _group_recipients_batch(
        organization, groups, retained, revoked_at
    )
    return _mail_all_groups(
        service, groups, recipients_by_group, shared, actor, share_action
    )


def _resolve_share(
    organization: Organization, actor_id: int, resource_kind: str, resource_id: str
) -> tuple[User, _SharedResource] | None:
    """The actor and resolved resource, or ``None`` to skip (already logged)."""
    actor = _get_user(organization, actor_id)
    shared = _load_resource(organization, resource_kind, resource_id)
    if actor is None:
        # Actor left the org between the share and the send -- routine race,
        # not a bug.
        logger.info(
            "metric=group_notification_actor_left_org_total group-notification: "
            "skipping resource share for %s/%s (actor no longer in org)",
            resource_kind,
            resource_id,
        )
        return None
    if shared.type is None:
        # A registered resource kind with no notification-plugin type mapping
        # -- a real gap worth an operator's attention, unlike the actor case.
        logger.warning(
            "metric=group_notification_unresolved_resource_type_total "
            "group-notification: skipping resource share for %s/%s "
            "(resource type not registered)",
            resource_kind,
            resource_id,
        )
        return None
    return actor, shared


def _mail_all_groups(
    service: Any,
    groups: list[OrganizationGroup],
    recipients_by_group: dict[int, list[User]],
    shared: _SharedResource,
    actor: User,
    share_action: str,
) -> bool:
    """Send each group's copy concurrently.

    Returns ``False`` (ask for redelivery) only when every attempted group
    genuinely failed to send. A skipped group (the plugin's tri-state
    ``None`` -- unconfigured, disabled, bad input) never counts as a failure.
    A *partial* failure -- some groups sent, others didn't -- is deliberately
    not retried either: redelivery would re-mail the groups that already
    succeeded, which is the exact duplication the worker's own retry
    classification exists to avoid. The lost group is logged instead.
    """
    to_mail = [g for g in groups if recipients_by_group.get(g.pk)]
    for group in groups:
        logger.info(
            "group-notification: task=notify_resource_shared_with_group "
            "group_id=%s action=%s recipient_count=%d",
            group.pk,
            share_action,
            len(recipients_by_group.get(group.pk, [])),
        )
    if not to_mail:
        return True

    def _send(group: OrganizationGroup) -> bool | None:
        return _mail_group(
            service, group, recipients_by_group[group.pk], shared, actor, share_action
        )

    workers = min(len(to_mail), _MAX_CONCURRENT_GROUP_SENDS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # list() first: pool.map returns a lazy generator, and all() stopping
        # at the first False would cancel every pending future past it --
        # groups later in the batch would silently never be mailed at all.
        results = list(pool.map(_send, to_mail))
    failed = [g.pk for g, r in zip(to_mail, results, strict=True) if r is False]
    if not failed:
        return True
    if len(failed) == len(to_mail):
        return False
    logger.error(
        "metric=group_notification_partial_failure_total failed_group_ids=%s "
        "of %d attempted",
        failed,
        len(to_mail),
    )
    return True


def send_membership_changed(
    *,
    organization: Organization,
    group_id: int,
    actor_id: int,
    membership_action: str,
    user_ids: Iterable[int],
) -> bool:
    """Mail the users whose membership of ``group_id`` just changed.

    Recipients are re-validated against ``OrganizationMember`` — this is where
    the offboarding race closes, for removals as well as additions: leaving a
    group does not remove someone from the org, so both directions validate the
    same way.

    Returns:
        ``False`` only when there were real recipients and the plugin reported
        a send failure. See :func:`send_resource_shared` for the full contract.
    """
    service = _service()
    if service is None:
        return True
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
        return True
    recipients = _live_member_users(organization, user_ids)
    logger.info(
        "group-notification: task=%s group_id=%s action=%s recipient_count=%d",
        "notify_group_membership_changed",
        group.pk,
        membership_action,
        len(recipients),
    )
    if not recipients:
        return True
    result = service.send_group_membership_notification(
        group_name=group.name,
        membership_action=MembershipAction(membership_action).value,
        recipients=recipients,
        actor=actor,
        organization=organization,
    )
    # Tri-state from the plugin: None (skipped -- unconfigured, disabled, bad
    # input) is not a failure, only an explicit False is.
    return result is not False


def _service() -> Any | None:
    """The cloud email service, or ``None`` when the plugin is absent (OSS)."""
    if not notification_plugin:
        # An absent plugin is normal in OSS. Absent while email is switched on
        # can only be a broken build, and the plugin loader swallows the import
        # error at DEBUG, so this is the only place it can surface.
        if getattr(settings, "ENABLE_EMAIL_NOTIFICATIONS", False):
            logger.warning(
                "group-notification: email is enabled but the notification "
                "plugin did not load — no mail is being sent"
            )
        else:
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


def _retained_user_ids(
    organization: Organization, resource: Any, share_action: str
) -> set[int] | None:
    """Users who still reach ``resource``; empty on the share direction.

    A revoked group's members may keep access by a route the revoke did not
    touch — another group, a direct share, ownership, or being an org admin,
    who reaches every resource in the org. Telling any of them their access was
    removed would be wrong, and the revoke email also repoints their CTA at the
    dashboard. ``compute_effective_members`` covers the share routes only, so
    owners and admins are added back explicitly.

    ``None`` means access never depended on the share at all, so the caller
    skips the fan-out entirely.
    """
    if share_action != ShareAction.REVOKED.value:
        return set()
    from tenant_account_v2.sharing_helpers import retained_user_ids

    retained = retained_user_ids(resource, organization)
    if retained is None:
        logger.info(
            "group-notification: revoke on %s, whose access does not depend on "
            "shares — nobody lost access, no mail",
            resource.pk,
        )
    return retained


def _groups_to_mail(
    organization: Organization,
    group_ids: Iterable[int],
    resource: Any,
    share_action: str,
) -> Iterable[OrganizationGroup]:
    """Groups from the payload that should still be mailed.

    On a grant, drop any group whose access was revoked between enqueue and
    delivery: the mail carries the resource name and id, so announcing access
    the group no longer holds discloses both to members who cannot reach it.
    The revoke direction needs no such check — its share row is already gone,
    and ``_retained_user_ids`` covers who kept access another way.
    """
    groups = _groups_in_org(organization, group_ids)
    if share_action != ShareAction.SHARED.value:
        return groups
    from tenant_account_v2.sharing_helpers import get_resource_share_groups

    live = {group.pk for group in get_resource_share_groups(resource)}
    to_mail = [group for group in groups if group.pk in live]
    if len(to_mail) != len(groups):
        logger.info(
            "group-notification: dropped %d of %d groups (access revoked since enqueue)",
            len(groups) - len(to_mail),
            len(groups),
        )
    return to_mail


def _group_recipients_batch(
    organization: Organization,
    groups: list[OrganizationGroup],
    retained: set[int],
    joined_before: datetime | None = None,
) -> dict[int, list[User]]:
    """Live members of each of ``groups`` who did not keep access via ``retained``.

    Two queries total (one ``GroupMembership`` scan, one ``OrganizationMember``
    validation) across every group in the fan-out, rather than one pair per
    group -- a resource shared with N groups issued N pairs of queries before
    this, since ``joined_before`` (a revoke's timestamp) is the same
    cutoff for every group being mailed in one call, so the membership lookup
    batches cleanly.

    ``joined_before`` drops anyone who joined after the access was taken away:
    they never held it through this group, so a revocation notice would be
    about access they never had.
    """
    if not groups:
        return {}
    memberships = GroupMembership.objects.filter(group__in=groups)
    if joined_before is not None:
        memberships = memberships.filter(created_at__lte=joined_before)
    user_ids_by_group: dict[int, set[int]] = defaultdict(set)
    all_user_ids: set[int] = set()
    for group_id, user_id in memberships.values_list("group_id", "user_id"):
        user_ids_by_group[group_id].add(user_id)
        all_user_ids.add(user_id)
    users_by_id = {
        user.pk: user for user in _live_member_users(organization, all_user_ids)
    }
    return {
        group.pk: [
            users_by_id[uid]
            for uid in user_ids_by_group.get(group.pk, ())
            if uid in users_by_id and uid not in retained
        ]
        for group in groups
    }


def _mail_group(
    service: Any,
    group: OrganizationGroup,
    recipients: list[User],
    shared: _SharedResource,
    actor: User,
    share_action: str,
) -> bool | None:
    """Send one group's copy of the resource-share email.

    Passes through the plugin's tri-state result -- see
    :func:`_mail_all_groups` for how ``None`` (skipped) is distinguished
    from ``False`` (genuinely failed).
    """
    return service.send_group_resource_shared_notification(
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

    Service accounts are excluded, matching ``compute_effective_members``. Also
    drops anyone with a falsy ``email`` -- silently, since this list decides
    who has real recipients, and that in turn decides whether a group is
    attempted at all (and so whether a 502 can ever fire for it).
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
    # Populate the FK cache with the instance we already hold: the mail send
    # (``resource_instance.organization``) runs inside a pool thread, and a
    # lazy query there opens a connection ``close_old_connections`` never
    # cleans up (that hook only runs on the request thread).
    resource.organization = organization
    name = getattr(resource, descriptor.name_field, "") or ""
    return _SharedResource(resource, name, _resource_type_for(descriptor, resource))


def _resource_type_for(descriptor: ShareableResource, resource: Any) -> str | None:
    """Map a resource to the email plugin's ``ResourceType`` value.

    Returns ``None`` for resources the plugin has no type for (e.g. a pipeline
    that is neither ETL nor TASK) — the caller skips rather than guessing.
    """
    if descriptor.kind == "pipeline":
        return pipeline_notification_type(getattr(resource, "pipeline_type", None))
    if descriptor.kind == "adapter_instance":
        return adapter_notification_type(str(resource.adapter_type or ""))
    return _STATIC_RESOURCE_TYPES.get(descriptor.kind)
