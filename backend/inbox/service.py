"""Writes and counts inbox items."""

from collections.abc import Iterable
from typing import Any

from account_v2.models import Organization, User
from utils.user_context import UserContext

from inbox.models import InboxItem


def notify(
    users: Iterable[User],
    *,
    kind: str,
    title: str,
    dedupe_key: str,
    body: str = "",
    route: dict[str, Any] | None = None,
    organization: Organization | None = None,
) -> None:
    """Add one item per user; an event already delivered to a user is skipped."""
    organization = organization or UserContext.get_organization()
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
            for user in {u.pk: u for u in users}.values()
        ],
        ignore_conflicts=True,
    )


def unread_count(user: User) -> int:
    return InboxItem.objects.filter(user=user, read_at__isnull=True).count()
