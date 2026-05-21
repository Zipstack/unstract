import logging
from typing import Any

from django.db import IntegrityError

from account_v2.custom_exceptions import AmbiguousUserException
from account_v2.models import User
from account_v2.user_filter_registry import UserFilterRegistry

Logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
    ) -> None:
        pass

    def create_or_update_user(self, email: str, user_id: str, provider: str) -> Any:
        try:
            user, created = User.objects.get_or_create(
                email=email, user_id=user_id, username=user_id, auth_provider=provider
            )
            if created:
                Logger.debug("User created successfully")
            return user
        except IntegrityError as error:
            Logger.info(f"[Duplicate Id] Failed to create User Error: {error}")
            raise error

    def create_user(self, email: str, user_id: str) -> User:
        try:
            user: User = User(email=email, user_id=user_id, username=email)
            user.save()
        except IntegrityError as error:
            Logger.info(f"[Duplicate Id] Failed to create User Error: {error}")
            raise error
        return user

    def update_user(self, user: User, user_id: str) -> User:
        user.user_id = user_id
        user.save()
        return user

    def get_user_by_email(self, email: str) -> User | None:
        return _resolve_unique(
            User.objects.filter(email=email, auth_provider=""),
            "user",
            ("email", email),
        )

    def get_user_by_user_id(self, user_id: str) -> Any:
        return _resolve_unique(
            User.objects.filter(user_id=user_id),
            "user",
            ("user_id", user_id),
        )

    def get_user_by_id(self, id: str) -> Any:
        """Retrieve a user by primary key.

        PK lookups are always unique and bypass the filter registry so
        identity-scoping filters cannot hide a row whose PK is already known
        (e.g., the currently authenticated admin's own row).
        """
        try:
            return User.objects.get(id=id)
        except User.DoesNotExist:
            return None


def _resolve_unique(
    qs: Any,
    kind: str,
    lookup: tuple[str, Any],
) -> User | None:
    """Apply the user filter registry and resolve to a single row.

    Raises ``AmbiguousUserException`` if more than one row matches after
    filters apply — that signals either duplicate User rows or a
    misconfigured identity-scoping filter, and silently picking one would
    propagate the wrong identity downstream.
    """
    qs = UserFilterRegistry.apply(qs, kind)
    rows = list(qs[:2])
    if len(rows) > 1:
        total = qs.count()
        field, value = lookup
        Logger.error(
            "Ambiguous User lookup for %s=%s (matched %d rows after filters)",
            field,
            value,
            total,
        )
        raise AmbiguousUserException()
    return rows[0] if rows else None
