import logging
import uuid
from typing import Any, Optional

from account.models import Organization, PlatformKey, User
from django.db import IntegrityError, connection
from django_tenants.utils import get_tenant_model
from platform_settings.exceptions import (
    ActiveKeyNotFound,
    DuplicateData,
    InternalServiceError,
)
from tenant_account.constants import ErrorMessage, PlatformServiceConstants

logger = logging.getLogger(__name__)


class PlatformAuthenticationService:
    """Service class to hold Platform service authentication and validation.

    Supports generation, refresh, revoke and toggle of active keys.
    """

    @staticmethod
    def generate_platform_key(
        is_active: bool,
        key_name: str,
        user: User,
        organization: Optional[Organization] = None,
    ) -> dict[str, Any]:
        """Method to support generation of new platform key. Throws error when
        maximum count is exceeded. Forbids for user other than admin
        permission.

        Args:
            key_name (str): Value of the key
            is_active (bool): By default the key is False
            user (User): User object representing the user generating the key
            organization (Optional[Organization], optional):
                Org the key belongs to. Defaults to None.

        Returns:
            dict[str, Any]:
                A dictionary containing the generated platform key details,
                    including the id, key name, and key value.
        Raises:
            DuplicateData: If a platform key with the same key name
                already exists for the organization.
            InternalServiceError: If an internal error occurs while
                generating the platform key.
        """
        organization = organization or connection.tenant
        if not organization:
            raise InternalServiceError("No valid organization provided")
        try:
            # TODO : Add encryption to Platform keys
            # id is added here to avoid passing of keys in transactions.
            platform_key: PlatformKey = PlatformKey(
                id=str(uuid.uuid4()),
                key=str(uuid.uuid4()),
                is_active=is_active,
                organization=organization,
                key_name=key_name,
                created_by=user,
                modified_by=user,
            )
            platform_key.save()
            result: dict[str, Any] = {}
            result[PlatformServiceConstants.ID] = platform_key.id
            result[PlatformServiceConstants.KEY_NAME] = platform_key.key_name
            result[PlatformServiceConstants.KEY] = platform_key.key

            logger.info(f"platform_key is generated for {organization.id}")
            return result
        except IntegrityError as error:
            logger.error(f"Integrity error - failed to generate platform key : {error}")
            raise DuplicateData(
                f"{ErrorMessage.KEY_EXIST}, \
                            {ErrorMessage.DUPLICATE_API}"
            )
        except Exception as error:
            logger.error(f"Failed to generate platform key : {error}")
            raise InternalServiceError()

    @staticmethod
    def delete_platform_key(id: str) -> None:
        """This is a delete operation. Use this function only if you know what
        you are doing.

        Args:
            id (str): _description_

        Raises:
            error: _description_
        """
        try:
            platform_key: PlatformKey = PlatformKey.objects.get(pk=id)
            platform_key.delete()
            logger.info(f"platform_key {id} is deleted")
        except IntegrityError as error:
            logger.error(f"Failed to delete platform key : {error}")
            raise DuplicateData(
                f"{ErrorMessage.KEY_EXIST}, \
                            {ErrorMessage.DUPLICATE_API}"
            )
        except Exception as error:
            logger.error(f"Failed to delete platform key : {error}")
            raise InternalServiceError()

    @staticmethod
    def refresh_platform_key(id: str, user: User) -> dict[str, Any]:
        """Method to refresh a platform key.

        Args:
            id (str): Unique id of the key to be refreshed
            new_key (str): Value to be updated.

        Raises:
            error: IntegrityError
        """
        try:
            result: dict[str, Any] = {}
            platform_key: PlatformKey = PlatformKey.objects.get(pk=id)
            platform_key.key = str(uuid.uuid4())
            platform_key.modified_by = user
            platform_key.save()
            result[PlatformServiceConstants.ID] = platform_key.id
            result[PlatformServiceConstants.KEY_NAME] = platform_key.key_name
            result[PlatformServiceConstants.KEY] = platform_key.key

            logger.info(f"platform_key {id} is updated by user {user.id}")
            return result
        except IntegrityError as error:
            logger.error(f"Integrity error - failed to refresh platform key : {error}")
            raise DuplicateData(
                f"{ErrorMessage.KEY_EXIST}, \
                            {ErrorMessage.DUPLICATE_API}"
            )
        except Exception as error:
            logger.error(f"Failed to refresh platform key : {error}")
            raise InternalServiceError()

    @staticmethod
    def toggle_platform_key_status(
        platform_key: PlatformKey, action: str, user: User
    ) -> None:
        """Method to activate/deactivate a platform key. Only one active key is
        allowed at a time. On change or setting, other keys are deactivated.

        Args:
            id (str): Id of the key to be toggled.
            action (str): activate/deactivate

        Raises:
            error: IntegrityError
        """
        try:
            organization = connection.tenant
            platform_key.modified_by = user
            if action == PlatformServiceConstants.ACTIVATE:
                active_keys: list[PlatformKey] = PlatformKey.objects.filter(
                    is_active=True, organization=organization
                ).all()
                # Deactivates all keys
                for key in active_keys:
                    key.is_active = False
                    key.modified_by = user
                    key.save()
                # Activates the chosen key.
                platform_key.is_active = True
                platform_key.save()
            if action == PlatformServiceConstants.DEACTIVATE:
                platform_key.is_active = False
                platform_key.save()
        except IntegrityError as error:
            logger.error(
                "IntegrityError - Failed to activate/deactivate "
                f"platform key : {error}"
            )
            raise DuplicateData(
                f"{ErrorMessage.KEY_EXIST}, \
                            {ErrorMessage.DUPLICATE_API}"
            )
        except Exception as error:
            logger.error(f"Failed to activate/deactivate platform key : {error}")
            raise InternalServiceError()

    @staticmethod
    def list_platform_key_ids() -> list[PlatformKey]:
        """Method to fetch list of platform keys unique ids for internal usage.

        Returns:
            Any: List of platform keys.
        """
        try:
            organization_id = connection.tenant.id
            platform_keys: list[PlatformKey] = PlatformKey.objects.filter(
                organization=organization_id
            )
            return platform_keys
        except Exception as error:
            logger.error(f"Failed to fetch platform key ids : {error}")
            raise InternalServiceError()

    @staticmethod
    def fetch_platform_key_id() -> Any:
        """Method to fetch list of platform keys unique ids for internal usage.

        Returns:
            Any: List of platform keys.
        """
        try:
            platform_key: list[PlatformKey] = PlatformKey.objects.all()
            return platform_key
        except Exception as error:
            logger.error(f"Failed to fetch platform key ids : {error}")
            raise InternalServiceError()

    @staticmethod
    def get_active_platform_key(
        organization_id: Optional[str] = None,
    ) -> PlatformKey:
        """Method to fetch active key.

        Considering only one active key is allowed at a time
        Returns:
            Any: platformKey.
        """
        try:
            organization_id = organization_id or connection.tenant.schema_name
            organization: Organization = get_tenant_model().objects.get(
                schema_name=organization_id
            )
            platform_key: PlatformKey = PlatformKey.objects.get(
                organization=organization, is_active=True
            )
            return platform_key
        except PlatformKey.DoesNotExist:
            raise ActiveKeyNotFound()
        except Exception as error:
            logger.error(f"Failed to fetch platform key : {error}")
            raise InternalServiceError()
