"""Enqueue hooks for group-sharing email notifications (UN-3494 / mfbt UNS-848).

Two events earn a group's members an email: a resource shared with or revoked
from the group, and a user added to or removed from it. Both are dispatched
asynchronously — the caller's request returns as soon as the write lands.

The sending itself runs in ``workers/``, which is Django-free, so the worker
task is a thin HTTP shim back to :mod:`tenant_account_v2.internal_views`; the
backend does the ORM and plugin work. Transport is resolved per-org by the same
``resolve_transport`` gate the execution path uses — the PG queue where that is
enabled, Celery otherwise.

The whole feature sits behind its own Flipt flag and fails closed everywhere: a
blind Flipt, a missing org, or any dispatch error means no notification, never
a broken share.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from tenant_account_v2.shareable_resources import kind_for_instance
from unstract.core.data_models import is_pg_transport
from unstract.flags.feature_flag import check_feature_flag_status

if TYPE_CHECKING:
    from account_v2.models import User

    from tenant_account_v2.models import OrganizationGroup

logger = logging.getLogger(__name__)

# Rollout flag for the whole feature. Sibling of ``pg_queue.flags`` — kept in
# one place so a grep on the constant finds every gate.
GROUP_NOTIFICATION_FLAG_KEY = "group_sharing_notifications_enabled"

NOTIFY_RESOURCE_SHARED_TASK = "notify_resource_shared_with_group"
NOTIFY_MEMBERSHIP_CHANGED_TASK = "notify_group_membership_changed"

# Mirrors the workers' ``QueueName.NOTIFICATION`` — a local literal so the
# backend does not import the workers package (same as ``pipeline_dispatch``).
NOTIFICATION_QUEUE = "notifications"


class MembershipAction(StrEnum):
    """What happened to a user's membership of a group."""

    ADDED = "added"
    REMOVED = "removed"


class ShareAction(StrEnum):
    """What happened to a group's access to a resource."""

    SHARED = "shared"
    REVOKED = "revoked"


def notify_resource_group_share_changed(
    *,
    resource: Any,
    added: Iterable[OrganizationGroup],
    removed: Iterable[OrganizationGroup],
    actor: User,
) -> None:
    """Queue group mail for a resource just shared with / revoked from groups."""
    for share_action, groups in (
        (ShareAction.SHARED, added),
        (ShareAction.REVOKED, removed),
    ):
        _notify_group_share(
            resource=resource, groups=groups, share_action=share_action, actor=actor
        )


def _notify_group_share(
    *,
    resource: Any,
    groups: Iterable[OrganizationGroup],
    share_action: ShareAction,
    actor: User,
) -> None:
    """Queue one group-share event.

    Recipients are resolved at delivery time rather than frozen here: anyone
    who leaves the org between the click and the send simply isn't in the fresh
    lookup, so offboarding safety costs nothing. Unlike a membership removal,
    revoking a group's access leaves the group and its members intact, so the
    fresh lookup still finds everyone who needs telling.
    """
    group_ids = sorted(group.pk for group in groups)
    if not group_ids:
        return
    organization_id = _organization_slug(resource)
    kind = kind_for_instance(resource)
    if not organization_id or kind is None or not _feature_enabled(organization_id):
        return
    _dispatch_quietly(
        task_name=NOTIFY_RESOURCE_SHARED_TASK,
        kwargs={
            "group_ids": group_ids,
            "actor_id": actor.pk,
            "resource_kind": kind,
            "resource_id": str(resource.pk),
            "share_action": str(share_action),
            "organization_id": organization_id,
        },
        organization_id=organization_id,
        entity_id=str(resource.pk),
    )


def notify_group_membership_changed(
    *,
    group: OrganizationGroup,
    action: MembershipAction,
    user_ids: Iterable[int],
    actor: User,
) -> None:
    """Queue "you were added to / removed from a group" mail for those users.

    Unlike a resource share, the user ids ride in the payload: on removal the
    membership rows are already gone by delivery time, and on add a fresh group
    lookup would mail every existing member too.
    """
    recipients = sorted(user_ids)
    if not recipients:
        return
    organization_id = _organization_slug(group)
    if not organization_id or not _feature_enabled(organization_id):
        return
    _dispatch_quietly(
        task_name=NOTIFY_MEMBERSHIP_CHANGED_TASK,
        kwargs={
            "group_id": group.pk,
            "actor_id": actor.pk,
            "membership_action": str(action),
            "user_ids": recipients,
            "organization_id": organization_id,
        },
        organization_id=organization_id,
        entity_id=str(group.pk),
    )


def _feature_enabled(organization_id: str) -> bool:
    """Whether group-sharing notifications are on for this org. Fails closed."""
    # Parse exactly as FliptClient does (``.lower()``, no ``.strip()``) so the
    # two can never disagree on a value like " true".
    if os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() != "true":
        return False
    try:
        return bool(
            check_feature_flag_status(
                flag_key=GROUP_NOTIFICATION_FLAG_KEY,
                entity_id=organization_id,
                context={"organization_id": organization_id},
            )
        )
    except Exception:
        logger.warning(
            "group-notification: Flipt evaluation failed for org %s; skipping",
            organization_id,
            exc_info=True,
        )
        return False


def _organization_slug(obj: Any) -> str | None:
    """The owning org's string identifier (``Organization.organization_id``).

    This is the ``X-Organization-ID`` value the worker echoes back, not the DB
    pk, and it is what ``resolve_transport`` expects.
    """
    organization = getattr(obj, "organization", None)
    return getattr(organization, "organization_id", None)


def _dispatch_quietly(
    *,
    task_name: str,
    kwargs: dict[str, Any],
    organization_id: str,
    entity_id: str,
) -> None:
    """Dispatch on the resolved transport; never let a failure reach the caller.

    The share or membership change has already been committed by the time this
    runs — losing its email is not a reason to fail the request the user made.
    """
    try:
        _dispatch(
            task_name=task_name,
            kwargs=kwargs,
            organization_id=organization_id,
            entity_id=entity_id,
        )
    except Exception:
        logger.exception(
            "group-notification: failed to dispatch %s for org %s",
            task_name,
            organization_id,
        )


def _dispatch(
    *,
    task_name: str,
    kwargs: dict[str, Any],
    organization_id: str,
    entity_id: str,
) -> None:
    # Lazy imports — ``backend.celery_service`` and ``pg_queue`` are heavier
    # than this leaf module and importing them at load time risks a cycle
    # during Django app loading.
    from pg_queue.producer import enqueue_task
    from workflow_manager.workflow_v2.transport import resolve_transport

    from backend.celery_service import app as celery_app

    transport = resolve_transport(execution_id=entity_id, organization_id=organization_id)
    if is_pg_transport(transport):
        msg_id = enqueue_task(
            task_name=task_name,
            queue=NOTIFICATION_QUEUE,
            kwargs=kwargs,
            org_id=organization_id,
        )
        logger.info(
            "group-notification: %s enqueued on PG queue %r (msg_id=%s)",
            task_name,
            NOTIFICATION_QUEUE,
            msg_id,
        )
        return
    celery_app.send_task(task_name, kwargs=kwargs, queue=NOTIFICATION_QUEUE)
    logger.info("group-notification: %s dispatched on Celery", task_name)
