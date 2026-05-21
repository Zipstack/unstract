"""Pluggable filters for User / OrganizationMember queries.

Plugins (e.g., the auth0 plugin) can register a callable that scopes
querysets to a subset of users — for example, only users whose Auth0
user_id belongs to the current environment's OIDC connection. Core
services call ``UserFilterRegistry.apply`` on every user lookup so the
registered filters take effect uniformly without core needing to know
which plugin is loaded.

When no filters are registered the registry is a no-op, so OSS and
development setups are unaffected.
"""

from collections.abc import Callable
from typing import Literal

from django.db.models import QuerySet

# "user" filters operate on `account_v2.User` querysets and should
# reference `user_id`. "org_member" filters operate on
# `tenant_account_v2.OrganizationMember` querysets and should reference
# `user__user_id`.
FilterKind = Literal["user", "org_member"]

FilterFn = Callable[[QuerySet, FilterKind], QuerySet]


class UserFilterRegistry:
    _filters: list[FilterFn] = []

    @classmethod
    def register(cls, fn: FilterFn) -> None:
        if fn not in cls._filters:
            cls._filters.append(fn)

    @classmethod
    def apply(cls, qs: QuerySet, kind: FilterKind) -> QuerySet:
        for fn in cls._filters:
            qs = fn(qs, kind)
        return qs
