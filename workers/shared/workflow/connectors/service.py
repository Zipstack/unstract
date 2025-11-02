"""Worker-Native Connector Service

This module provides connector factory operations for workers.
"""

from typing import Any

# Import shared operations
from unstract.connectors.operations import ConnectorOperations

from ...api.internal_client import InternalAPIClient
from ...infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class WorkerConnectorService:
    """Factory service for creating destination connectors in workers"""

    def __init__(self, api_client: InternalAPIClient):
        """Initialize connector service.

        Args:
            api_client: API client (preserved for compatibility but unused)
        """
        self.api_client = api_client  # Preserved for compatibility

    def _get_destination_connector(
        self, connector_id: str, connector_settings: dict[str, Any]
    ):
        """Get destination connector using exact backend registry pattern.

        This method uses the same connector registry pattern as:
        - backend/workflow_manager/endpoint_v2/destination.py
        - backend/workflow_manager/endpoint_v2/base_connector.py

        Args:
            connector_id: Connector ID from registry (not connection_type)
            connector_settings: Connector configuration settings

        Returns:
            Connector instance
        """
        return ConnectorOperations.get_fs_connector(
            connector_id=connector_id, settings=connector_settings
        )
