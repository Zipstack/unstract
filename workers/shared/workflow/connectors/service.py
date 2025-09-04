"""Worker-Native Connector Service

This module provides connector factory operations for workers.
"""

from typing import Any

# Import shared operations
from unstract.connectors.operations import ConnectorOperations

from ...api.facades.legacy_client import InternalAPIClient
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

        Raises:
            ValueError: If connector_id is not supported
            ImportError: If connector registry not available
        """
        try:
            # Try filesystem connector first
            try:
                return ConnectorOperations.get_fs_connector(
                    connector_id=connector_id, settings=connector_settings
                )
            except ValueError:
                # Final fallback - legacy connection_type handling for backward compatibility
                return self._get_legacy_connector(connector_id, connector_settings)

        except ImportError as e:
            raise ImportError(
                f"Connector registry not available for {connector_id}: {str(e)}"
            )

    def _get_legacy_connector(
        self, connection_type: str, connector_settings: dict[str, Any]
    ):
        """Legacy connector factory for backward compatibility.

        This method is kept for backward compatibility with existing workflows
        that still use connection_type instead of connector_id.

        Args:
            connection_type: Legacy connection type
            connector_settings: Connector configuration settings

        Returns:
            Connector instance

        Raises:
            ValueError: If connection type is not supported
        """
        connection_type_upper = connection_type.upper()

        # Map legacy connection types to probable connector IDs and try registry first
        legacy_mapping = {
            "FILESYSTEM": "LOCAL_STORAGE",
            "LOCAL_FS": "LOCAL_STORAGE",
            "LOCAL": "LOCAL_STORAGE",
            "S3": "S3",
            "AWS_S3": "S3",
            "GCS": "GCS",
            "GOOGLE_CLOUD_STORAGE": "GCS",
            "POSTGRESQL": "POSTGRESQL",
            "POSTGRES": "POSTGRESQL",
            "MYSQL": "MYSQL",
            "BIGQUERY": "BIGQUERY",
            "SNOWFLAKE": "SNOWFLAKE",
        }

        # Try to map to actual connector ID
        if connection_type_upper in legacy_mapping:
            try:
                mapped_connector_id = legacy_mapping[connection_type_upper]
                return self._get_destination_connector(
                    mapped_connector_id, connector_settings
                )
            except (ValueError, ImportError):
                pass

        # Final fallback - raise error with helpful message
        raise ValueError(
            f"Unsupported destination connector: {connection_type}. "
            f"Please use connector_id from the connector registry instead of connection_type."
        )
