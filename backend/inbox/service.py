"""Writes and counts inbox items."""

import logging
import queue
import threading
from collections.abc import Iterable
from typing import Any

from account_v2.models import Organization, User
from django.db import transaction
from django.db.models import Count
from utils.user_context import UserContext

from inbox.models import InboxItem

logger = logging.getLogger(__name__)

UNREAD_EVENT = "inbox:unread"

# Pushes go to one background thread per process: a socket publish retries
# without limit while the broker is down, and must not hold a request. A full
# backlog drops new pushes; the list endpoint stays the source of truth.
_queue: queue.Queue = queue.Queue(maxsize=1000)
_publisher: threading.Thread | None = None
_publisher_lock = threading.Lock()
_dropping = False  # one warning per stretch of dropped pushes


def _publish_next() -> None:
    room, event, data = _queue.get()
    try:
        from utils import log_events

        log_events._emit_websocket_event(room, event, data)
    except Exception:
        logger.exception("Could not push an inbox count")


def _publish_forever() -> None:
    while True:
        _publish_next()


def _ensure_publisher() -> None:
    global _publisher
    with _publisher_lock:
        # Checked on each push: a forked worker process inherits no threads.
        if _publisher is None or not _publisher.is_alive():
            _publisher = threading.Thread(
                target=_publish_forever, name="inbox-push", daemon=True
            )
            _publisher.start()


def _submit(room: str, event: str, data: dict[str, Any]) -> None:
    global _dropping
    _ensure_publisher()
    try:
        _queue.put_nowait((room, event, data))
        _dropping = False
    except queue.Full:
        if not _dropping:
            logger.warning(
                "Inbox push backlog is full; dropping pushes while it stays full"
            )
        _dropping = True


def notify(
    users: Iterable[User],
    *,
    kind: str,
    title: str,
    dedupe_key: str,
    body: str = "",
    route: dict[str, Any] | None = None,
    organization: Organization | None = None,
    refresh: bool = False,
    push: bool = True,
) -> None:
    """Add one item per user; an event already delivered to a user is skipped.

    ``refresh=True`` instead overwrites a user's existing item for the same
    ``dedupe_key``: new text and route, unread again, and moved to the top.
    ``push=False`` leaves the new count to the user's next list call.
    """
    organization = organization or UserContext.get_organization()
    if organization is None:
        # A NULL organization would also escape the one-item-per-event constraint.
        raise ValueError("An inbox item needs an organization")
    users = {u.pk: u for u in users}
    # A savepoint, so a failed insert never breaks the caller's transaction.
    with transaction.atomic():
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
                # A fixed order, so two writers upserting the same rows cannot deadlock.
                for user in sorted(users.values(), key=lambda u: u.pk)
            ],
            **(
                {
                    "update_conflicts": True,
                    "unique_fields": ["organization", "user", "dedupe_key"],
                    "update_fields": ["title", "body", "route", "read_at", "created_at"],
                }
                if refresh
                else {"ignore_conflicts": True}
            ),
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
                _submit(
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
