import json
import logging
from typing import Any, Optional

import adapter_processor
from account.models import User
from adapter_processor.constants import AdapterKeys
from adapter_processor.exceptions import (
    InternalServiceError,
    InValidAdapterId,
    TestAdapterException,
)
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from platform_settings.platform_auth_service import (
    PlatformAuthenticationService,
)
from unstract.adapters.adapterkit import Adapterkit
from unstract.adapters.base import Adapter
from unstract.adapters.enums import AdapterTypes
from unstract.adapters.exceptions import AdapterError
from unstract.adapters.x2text.constants import X2TextConstants

from .models import AdapterInstance

logger = logging.getLogger(__name__)


class AdapterProcessor:
    @staticmethod
    def get_json_schema(adapter_id: str) -> dict[str, Any]:
        """Function to return JSON Schema for Adapters."""
        schema_details: dict[str, Any] = {}
        updated_adapters = AdapterProcessor.__fetch_adapters_by_key_value(
            AdapterKeys.ID, adapter_id
        )
        if len(updated_adapters) != 0:
            try:
                schema_details[AdapterKeys.JSON_SCHEMA] = json.loads(
                    updated_adapters[0].get(AdapterKeys.JSON_SCHEMA)
                )
            except Exception as exc:
                logger.error(f"Error occured while parsing JSON Schema : {exc}")
                raise InternalServiceError()
        else:
            logger.error(
                f"Invalid adapter Id : {adapter_id} while fetching JSON Schema"
            )
            raise InValidAdapterId()
        return schema_details

    @staticmethod
    def get_all_supported_adapters(type: str) -> list[dict[Any, Any]]:
        """Function to return list of all supported adapters."""
        supported_adapters = []
        updated_adapters = []
        updated_adapters = AdapterProcessor.__fetch_adapters_by_key_value(
            AdapterKeys.ADAPTER_TYPE, type
        )
        for each_adapter in updated_adapters:
            supported_adapters.append(
                {
                    AdapterKeys.ID: each_adapter.get(AdapterKeys.ID),
                    AdapterKeys.NAME: each_adapter.get(AdapterKeys.NAME),
                    AdapterKeys.DESCRIPTION: each_adapter.get(
                        AdapterKeys.DESCRIPTION
                    ),
                    AdapterKeys.ICON: each_adapter.get(AdapterKeys.ICON),
                    AdapterKeys.ADAPTER_TYPE: each_adapter.get(
                        AdapterKeys.ADAPTER_TYPE
                    ),
                }
            )
        return supported_adapters

    @staticmethod
    def get_adapter_data_with_key(adapter_id: str, key_value: str) -> Any:
        """Generic Function to get adapter data with provided key."""
        updated_adapters = AdapterProcessor.__fetch_adapters_by_key_value(
            "id", adapter_id
        )
        if len(updated_adapters) == 0:
            logger.error(
                f"Invalid adapter ID {adapter_id} while invoking utility"
            )
            raise InValidAdapterId()
        return AdapterProcessor.__fetch_adapters_by_key_value("id", adapter_id)[
            0
        ].get(key_value)

    @staticmethod
    def test_adapter(adapter_id: str, adapter_metadata: dict[str, Any]) -> bool:
        logger.info(f"Testing adapter: {adapter_id}")
        try:
            adapter_class = Adapterkit().get_adapter_class_by_adapter_id(
                adapter_id
            )

            if (
                adapter_metadata.pop(AdapterKeys.ADAPTER_TYPE)
                == AdapterKeys.X2TEXT
            ):
                adapter_metadata[
                    X2TextConstants.X2TEXT_HOST
                ] = settings.X2TEXT_HOST
                adapter_metadata[
                    X2TextConstants.X2TEXT_PORT
                ] = settings.X2TEXT_PORT
                platform_key = (
                    PlatformAuthenticationService.get_active_platform_key()
                )
                adapter_metadata[
                    X2TextConstants.PLATFORM_SERVICE_API_KEY
                ] = str(platform_key.key)

            adapter_instance = adapter_class(adapter_metadata)
            test_result: bool = adapter_instance.test_connection()
            logger.info(f"{adapter_id} test result: {test_result}")
            return test_result
        except AdapterError as e:
            raise TestAdapterException(str(e))

    @staticmethod
    def __fetch_adapters_by_key_value(key: str, value: Any) -> Adapter:
        """Fetches a list of adapters that have an attribute matching key and
        value."""
        logger.info(f"Fetching adapter list for {key} with {value}")
        adapter_kit = Adapterkit()
        adapters = adapter_kit.get_adapters_list()
        return [iterate for iterate in adapters if iterate[key] == value]

    @staticmethod
    def set_default_triad(default_triad: dict[str, str], user: User) -> None:
        filter_params: dict[str, Any] = {}

        try:
            for key in default_triad:
                filter_params.clear()
                adapter_id = default_triad[key]
                # Query rows where adapter_type=X and is_default=True
                if key == AdapterKeys.LLM_DEFAULT:
                    adapter_type = AdapterTypes.LLM.name
                elif key == AdapterKeys.EMBEDDING_DEFAULT:
                    adapter_type = AdapterTypes.EMBEDDING.name
                elif key == AdapterKeys.VECTOR_DB_DEFAULT:
                    adapter_type = AdapterTypes.VECTOR_DB.name
                elif key == AdapterKeys.X2TEXT_DEFAULT:
                    adapter_type = AdapterTypes.X2TEXT.name

                filter_params["adapter_type"] = adapter_type
                filter_params["is_default"] = True
                filter_params["created_by"] = user

                AdapterInstance.objects.filter(**filter_params).update(
                    is_default=False
                )

                # Update the adapter_id in the incoming
                # list to set is_default=True
                filter_params.clear()
                try:
                    new_adapter_default: AdapterInstance = (
                        AdapterInstance.objects.get(pk=adapter_id)
                    )
                    new_adapter_default.is_default = True
                    new_adapter_default.save()
                except (
                    adapter_processor.models.AdapterInstance.DoesNotExist
                ) as e:
                    logger.error(
                        f"Error while retrieving adapter: {adapter_id} "
                        f"reason: {e}"
                    )
                    raise InValidAdapterId()
            logger.info("Changed defaults successfully")
        except Exception as e:
            logger.error(f"Unable to save defaults because: {e}")
            if isinstance(e, InValidAdapterId):
                raise e
            else:
                raise InternalServiceError()

    @staticmethod
    def get_adapter_instance_by_id(adapter_instance_id: str) -> Adapter:
        """Get the adapter instance by its ID.

        Parameters:
        - adapter_instance_id (str): The ID of the adapter instance.

        Returns:
        - Adapter: The adapter instance with the specified ID.

        Raises:
        - Exception: If there is an error while fetching the adapter instance.
        """
        try:
            adapter = AdapterInstance.objects.get(id=adapter_instance_id)
        except Exception as e:
            logger.error(f"Unable to fetch adapter: {e}")
        if not adapter:
            logger.error("Unable to fetch adapter")
        return adapter.adapter_name

    @staticmethod
    def get_adapters_by_type(
        adapter_type: AdapterTypes, user: User
    ) -> list[AdapterInstance]:
        """Get a list of adapters by their type.

        Parameters:
        - adapter_type (AdapterTypes): The type of adapters to retrieve.

        Returns:
        - list[AdapterInstance]: A list of AdapterInstance objects that match
            the specified adapter type.
        """
        adapters: list[AdapterInstance] = AdapterInstance.objects.filter(
            adapter_type=adapter_type.value, created_by=user
        )
        return adapters

    @staticmethod
    def get_adapter_by_name_and_type(
        adapter_type: AdapterTypes,
        adapter_name: Optional[str] = None,
    ) -> Optional[AdapterInstance]:
        """Get the adapter instance by its name and type.

        Parameters:
        - adapter_name (str): The name of the adapter instance.
        - adapter_type (AdapterTypes): The type of the adapter instance.

        Returns:
        - AdapterInstance: The adapter with the specified name and type.
        """
        if adapter_name:
            adapter: AdapterInstance = AdapterInstance.objects.get(
                adapter_name=adapter_name, adapter_type=adapter_type.value
            )
        else:
            try:
                adapter = AdapterInstance.objects.get(
                    adapter_type=adapter_type.value, is_default=True
                )
            except AdapterInstance.DoesNotExist:
                return None
        return adapter

    @staticmethod
    def get_default_adapters(user: User) -> list[AdapterInstance]:
        """Retrieve a list of default adapter instances. This method queries
        the database to fetch all adapter instances marked as default.

        Raises:
            InternalServiceError: If an unexpected error occurs during
            the database query.

        Returns:
            list[AdapterInstance]: A list of AdapterInstance objects that are
            marked as default.
        """
        try:
            adapters: list[AdapterInstance] = AdapterInstance.objects.filter(
                is_default=True, created_by=user
            )
            return adapters
        except ObjectDoesNotExist as e:
            logger.error(f"No default adapters found: {e}")
            raise InternalServiceError("No default adapters found")
        except Exception as e:
            logger.error(f"Error occurred while fetching default adapters: {e}")
            raise InternalServiceError("Error fetching default adapters")
