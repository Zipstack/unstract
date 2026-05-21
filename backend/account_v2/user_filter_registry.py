"""Pluggable filters for User / OrganizationMember queries.

Identity plugins can register a callable that scopes querysets to a
subset of users — for example, limiting visibility to users whose
external identity belongs to the current environment. The service
layers in `account_v2.user.UserService` and
`tenant_account_v2.organization_member_service.OrganizationMemberService`
call ``UserFilterRegistry.apply`` on each user lookup so registered
filters take effect uniformly without core having to know which plugin
is loaded.

When no filters are registered the registry is a no-op, so OSS and
development setups are unaffected.
"""

import logging
from collections.abc import Callable
from typing import ClassVar, Literal

from django.db.models import QuerySet

logger = logging.getLogger(__name__)

# "user" filters operate on `account_v2.User` querysets and should
# reference `user_id`. "org_member" filters operate on
# `tenant_account_v2.OrganizationMember` querysets and should reference
# `user__user_id`.
FilterKind = Literal["user", "org_member"]

FilterFn = Callable[[QuerySet, FilterKind], QuerySet]


class UserFilterRegistry:
    _filters: ClassVar[list[FilterFn]] = []

    @classmethod
    def register(cls, fn: FilterFn) -> None:
        if fn not in cls._filters:
            cls._filters.append(fn)

    @classmethod
    def unregister(cls, fn: FilterFn) -> None:
        if fn in cls._filters:
            cls._filters.remove(fn)

    @classmethod
    def clear(cls) -> None:
        """Remove all registered filters. Intended for tests only."""
        cls._filters.clear()

    @classmethod
    def apply(cls, qs: QuerySet, kind: FilterKind) -> QuerySet:
        for fn in cls._filters:
            try:
                qs = fn(qs, kind)
            except Exception:
                logger.exception(
                    "user_filter plugin raised; aborting lookup (fn=%r kind=%s)",
                    fn,
                    kind,
                )
                raise
        return qs
