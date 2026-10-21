"""Writes and counts inbox items."""

import logging
from collections.abc import Iterable
from typing import Any

from account_v2.models import Organization, User
from django.db import transaction
from django.db.models import Count
from utils.user_context import UserContext

from inbox.models import InboxItem

logger = logging.getLogger(__name__)

UNREAD_EVENT = "inbox:unread"


def notify(
    users: Iterable[User],
    *,
    kind: str,
    title: str,
    dedupe_key: str,
    body: str = "",
    route: dict[str, Any] | None = None,
    organization: Organization | None = None,
    push: bool = True,
) -> None:
    """Add one item per user; an event already delivered to a user is skipped.

    ``push=False`` leaves the new count to the user's next list call.
    """
    organization = organization or UserContext.get_organization()
    users = {u.pk: u for u in users}
    InboxItem.objects.bulk_create(
        [
            InboxItem(
                organization=organization,
                user=user,
                kind=kind,
                title=title[:255],
                body=body,
                route=route,
                dedupe_key=dedupe_key,
            )
            for user in users.values()
        ],
        ignore_conflicts=True,
    )
    if push:
        push_unread(organization, users)


def unread_count(user: User) -> int:
    return InboxItem.objects.filter(user=user, read_at__isnull=True).count()


def push_unread(organization: Organization, user_ids: Iterable[Any]) -> None:
    """Send each user their unread count in socket room ``user:<id>`` after commit."""
    user_ids = list(user_ids)

    def send() -> None:
        try:
            from utils.log_events import _emit_websocket_event

            # Base manager: callers may run with no organization in context.
            counts = dict(
                InboxItem._base_manager.filter(
                    organization=organization,
                    user_id__in=user_ids,
                    read_at__isnull=True,
                )
                .values("user_id")
                .annotate(n=Count("id"))
                .values_list("user_id", "n")
            )
            for user_id in user_ids:
                _emit_websocket_event(
                    f"user:{user_id}",
                    UNREAD_EVENT,
                    {
                        "organization_id": organization.organization_id,
                        "unread_count": counts.get(user_id, 0),
                    },
                )
        except Exception:
            logger.exception("Could not push inbox counts")

    transaction.on_commit(send)
