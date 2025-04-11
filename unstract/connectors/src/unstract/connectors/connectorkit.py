import logging
from typing import Any

from singleton_decorator import singleton

from unstract.connectors import ConnectorDict  # type: ignore
from unstract.connectors.base import UnstractConnector
from unstract.connectors.constants import Common
from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.enums import ConnectorMode
from unstract.connectors.filesystems import connectors as fs_connectors
from unstract.connectors.queues import connectors as q_connectors

logger = logging.getLogger(__name__)


@singleton
class Connectorkit:
    def __init__(self) -> None:
        self._connectors: ConnectorDict = fs_connectors | db_connectors | q_connectors

    @property
    def connectors(self) -> ConnectorDict:
        return self._connectors

    def get_connector_class_by_connector_id(self, connector_id: str) -> UnstractConnector:
        if connector_id in self._connectors:
            connector_class: UnstractConnector = self._connectors[connector_id][
                Common.METADATA
            ][Common.CONNECTOR]
            return connector_class
        else:
            raise RuntimeError(f"Couldn't obtain connector for {connector_id}")

    # TODO: Remove after UN-225 is merged
    # Once workflow code from core is removed
    def get_connector_class_by_name(
        self, connector_name: str
    ) -> UnstractConnector | None:
        for (
            connector_id,
            connector_registry_metadata,
        ) in self._connectors.items():
            if (
                connector_registry_metadata[Common.METADATA][Common.CONNECTOR].__name__
                is connector_name
            ):
                connector_class: UnstractConnector = connector_registry_metadata[
                    Common.METADATA
                ][Common.CONNECTOR]
                return connector_class
        logging.error(f">> Connector '{connector_name}' not found in connectorkit")
        logging.error(f">> Connectors in connectorkit : {self._connectors.keys()}")
        return None

    def get_connector_by_id(
        self, connector_id: str, *args: Any, **kwargs: Any
    ) -> UnstractConnector:
        """Instantiates and returns a connector.

        Args:
            connector_id (str): Identifies connector to create

        Raises:
            RuntimeError: If the ID is invalid/connector is missing

        Returns:
            UnstractConnector: Concrete impl of the `UnstractConnector` base
        """
        connector_class: UnstractConnector = self.get_connector_class_by_connector_id(
            connector_id
        )
        return connector_class(*args, **kwargs)

    def get_connectors_list(
        self, mode: ConnectorMode | None = None
    ) -> list[dict[str, Any]]:
        connectors = []
        for (
            connector_id,
            connector_registry_metadata,
        ) in self._connectors.items():
            m: UnstractConnector = connector_registry_metadata[Common.METADATA][
                Common.CONNECTOR
            ]
            _id = m.get_id()
            name = m.get_name()
            json_schema = m.get_json_schema()
            desc = m.get_description()
            icon = m.get_icon()
            oauth = m.requires_oauth()
            python_social_auth_backend = m.python_social_auth_backend()
            can_read = m.can_read()
            can_write = m.can_write()
            connector_mode = m.get_connector_mode()
            if mode and mode != connector_mode:
                continue
            connectors.append(
                {
                    "id": _id,
                    "name": name,
                    "class_name": m.__name__,
                    "description": desc,
                    "icon": icon,
                    "type": "built-in-file",
                    "oauth": oauth,
                    "python_social_auth_backend": python_social_auth_backend,  # noqa
                    "can_read": can_read,
                    "can_write": can_write,
                    "json_schema": json_schema,
                    "connector_mode": connector_mode,
                }
            )
        return connectors
