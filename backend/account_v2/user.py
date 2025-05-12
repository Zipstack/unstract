import logging
from typing import Any

from django.db import IntegrityError

from account_v2.models import User

Logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
    ) -> None:
        pass

    def create_or_update_user(self, email: str, user_id: str) -> Any:
        try:
            user, created = User.objects.get_or_create(
                email=email, user_id=user_id, username=user_id
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
        try:
            user: User = User.objects.get(email=email)
            return user
        except User.DoesNotExist:
            return None

    def get_user_by_user_id(self, user_id: str) -> Any:
        try:
            return User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return None

    def get_user_by_id(self, id: str) -> Any:
        """Retrieve a user by their ID, taking into account the schema context.

        Args:
            id (str): The ID of the user.

        Returns:
            Any: The user object if found, or None if not found.
        """
        try:
            return User.objects.get(id=id)
        except User.DoesNotExist:
            return None
