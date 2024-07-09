# mypy: ignore-errors
import json
import logging
from typing import Any, Optional

from connector_processor.constants import ConnectorKeys
from connector_processor.exceptions import (
    InternalServiceError,
    InValidConnectorId,
    InValidConnectorMode,
    OAuthTimeOut,
    TestConnectorException,
    TestConnectorInputException,
)

from backend.constants import FeatureFlag
from unstract.connectors.base import UnstractConnector
from unstract.connectors.connectorkit import Connectorkit
from unstract.connectors.enums import ConnectorMode
from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.ucs import UnstractCloudStorage
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
    from connector_auth_v2.constants import ConnectorAuthKey
    from connector_auth_v2.pipeline.common import ConnectorAuthHelper
    from connector_v2.constants import ConnectorInstanceKey as CIKey
else:
    from connector.constants import ConnectorInstanceKey as CIKey
    from connector_auth.constants import ConnectorAuthKey
    from connector_auth.pipeline.common import ConnectorAuthHelper

logger = logging.getLogger(__name__)


def fetch_connectors_by_key_value(
    key: str, value: Any, connector_mode: Optional[ConnectorMode] = None
) -> list[UnstractConnector]:
    """Fetches a list of connectors that have an attribute matching key and
    value."""
    logger.info(f"Fetching connector list for {key} with {value}")
    connector_kit = Connectorkit()
    connectors = connector_kit.get_connectors_list(mode=connector_mode)
    return [iterate for iterate in connectors if iterate[key] == value]


class ConnectorProcessor:
    @staticmethod
    def get_json_schema(connector_id: str) -> dict:
        """Function to return JSON Schema for Connectors."""
        schema_details: dict = {}
        if connector_id == UnstractCloudStorage.get_id():
            return schema_details
        updated_connectors = fetch_connectors_by_key_value(
            ConnectorKeys.ID, connector_id
        )
        if len(updated_connectors) != 0:
            connector = updated_connectors[0]
            schema_details[ConnectorKeys.OAUTH] = connector.get(ConnectorKeys.OAUTH)
            schema_details[ConnectorKeys.SOCIAL_AUTH_URL] = connector.get(
                ConnectorKeys.SOCIAL_AUTH_URL
            )
            try:
                schema_details[ConnectorKeys.JSON_SCHEMA] = json.loads(
                    connector.get(ConnectorKeys.JSON_SCHEMA)
                )
            except Exception as exc:
                logger.error(f"Error occurred while parsing JSON Schema: {exc}")
                raise InternalServiceError()
        else:
            logger.error(
                f"Invalid connector Id : {connector_id} "
                f"while fetching "
                f"JSON Schema"
            )
            raise InValidConnectorId()
        return schema_details

    @staticmethod
    def get_all_supported_connectors(
        type: str, connector_mode: Optional[ConnectorMode] = None
    ) -> list[dict]:
        """Function to return list of all supported connectors except PCS."""
        supported_connectors = []
        updated_connectors = []
        if type == ConnectorKeys.INPUT:
            updated_connectors = fetch_connectors_by_key_value(
                ConnectorKeys.CAN_READ, True, connector_mode=connector_mode
            )
        if type == ConnectorKeys.OUTPUT:
            updated_connectors = fetch_connectors_by_key_value(
                ConnectorKeys.CAN_WRITE, True, connector_mode=connector_mode
            )

        for each_connector in updated_connectors:
            supported_connectors.append(
                {
                    ConnectorKeys.ID: each_connector.get(ConnectorKeys.ID),
                    ConnectorKeys.NAME: each_connector.get(ConnectorKeys.NAME),
                    ConnectorKeys.DESCRIPTION: each_connector.get(
                        ConnectorKeys.DESCRIPTION
                    ),
                    ConnectorKeys.ICON: each_connector.get(ConnectorKeys.ICON),
                    CIKey.CONNECTOR_MODE: each_connector.get(CIKey.CONNECTOR_MODE).name,
                }
            )

        return supported_connectors

    @staticmethod
    def test_connectors(connector_id: str, cred_string: dict[str, Any]) -> bool:
        logger.info(f"Testing connector: {connector_id}")
        connector: dict[str, Any] = fetch_connectors_by_key_value(
            ConnectorKeys.ID, connector_id
        )[0]
        if connector.get(ConnectorKeys.OAUTH):
            try:
                oauth_key = cred_string.get(ConnectorAuthKey.OAUTH_KEY)
                cred_string = ConnectorAuthHelper.get_oauth_creds_from_cache(
                    cache_key=oauth_key, delete_key=False
                )
            except Exception as exc:
                logger.error(
                    f"Error while testing file based OAuth supported "
                    f"connectors: {exc}"
                )
                raise OAuthTimeOut()

        try:
            connector_impl = Connectorkit().get_connector_by_id(
                connector_id, cred_string
            )
            test_result = connector_impl.test_credentials()
            logger.info(f"{connector_id} test result: {test_result}")
            return test_result
        except ConnectorError as e:
            logger.error(f"Error while testing {connector_id}: {e}")
            raise TestConnectorInputException(core_err=e)
        except Exception as e:
            logger.error(f"Error while testing {connector_id}: {e}")
            raise TestConnectorException

    def get_connector_data_with_key(connector_id: str, key_value: str) -> Any:
        """Generic Function to get connector data with provided key."""
        updated_connectors = fetch_connectors_by_key_value("id", connector_id)
        if len(updated_connectors) == 0:
            logger.error(f"Invalid connector ID {connector_id} while invoking utility")
            raise InValidConnectorId()
        return fetch_connectors_by_key_value("id", connector_id)[0].get(key_value)

    @staticmethod
    def validate_connector_mode(connector_mode: str) -> ConnectorMode:
        """Validate the connector mode.

        Parameters:
        - connector_mode (str): The connector mode to validate.

        Returns:
        - ConnectorMode: The validated connector mode.

        Raises:
        - InValidConnectorMode: If the connector mode is not valid.
        """
        try:
            connector_mode = ConnectorMode(connector_mode)
        except ValueError:
            raise InValidConnectorMode
        return connector_mode
