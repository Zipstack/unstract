"""Connector Operations for Unstract Platform

This module provides core connector operations for filesystem connectors
and connector health checks.

Used by:
- workers/shared/workflow/connectors/service.py (for worker-native operations)
"""

import logging
from typing import Any

# Import internal connector components (no try/catch needed - proper dependencies)
from unstract.connectors.constants import Common
from unstract.connectors.filesystems import connectors as fs_connectors
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


class ConnectorOperations:
    """Common connector operations shared between backend and workers with strict error handling"""

    @staticmethod
    def test_connector_connection(
        connector_id: str, settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Test connection to connector before attempting operations.

        Args:
            connector_id: Connector ID
            settings: Connector settings

        Returns:
            Dictionary with connection test results: {'is_connected': bool, 'error': str}
        """
        try:
            # Get connector instance
            connector = ConnectorOperations.get_fs_connector(connector_id, settings)

            # Test basic connectivity by getting fsspec filesystem
            fs = connector.get_fsspec_fs()

            # For filesystem connectors, try to check if root path exists
            test_path = settings.get("path", "/")
            try:
                fs.exists(test_path)
                return {"is_connected": True, "error": None}
            except Exception as path_error:
                return {
                    "is_connected": False,
                    "error": f"Cannot access path '{test_path}': {str(path_error)}",
                }

        except Exception as e:
            return {"is_connected": False, "error": str(e)}

    @staticmethod
    def get_fs_connector(
        connector_id: str, settings: dict[str, Any]
    ) -> "UnstractFileSystem":
        """Get filesystem connector instance using exact backend BaseConnector logic.

        This replicates backend/workflow_manager/endpoint_v2/base_connector.py:get_fs_connector()

        Args:
            connector_id: Connector ID from the registry
            settings: Connector-specific settings

        Returns:
            UnstractFileSystem instance

        Raises:
            ImportError: If connector registries not available (critical error)
            ValueError: If connector_id is not supported
        """
        if not fs_connectors:
            raise RuntimeError("Filesystem connectors registry not initialized")

        if connector_id not in fs_connectors:
            available_ids = list(fs_connectors.keys())
            raise ValueError(
                f"Connector '{connector_id}' is not supported. "
                f"Available connectors: {available_ids}"
            )

        if not Common:
            raise RuntimeError("Common connector constants not initialized")

        # Use exact same pattern as backend BaseConnector
        connector_class = fs_connectors[connector_id][Common.METADATA][Common.CONNECTOR]
        return connector_class(settings)

    @staticmethod
    def get_connector_health(source_config: dict[str, Any]) -> dict[str, Any]:
        """Get health status of a source connector.

        Args:
            source_config: Source configuration dictionary

        Returns:
            Dictionary with health status and metadata
        """
        try:
            connector_id = source_config.get("connector_id") or source_config.get(
                "connection_type"
            )
            settings = source_config.get("settings", {})

            if not connector_id or not settings:
                return {
                    "is_healthy": False,
                    "connection_type": connector_id,
                    "errors": ["Missing connector configuration"],
                    "response_time_ms": None,
                }

            import time

            start_time = time.time()

            # Test connection
            connection_result = ConnectorOperations.test_connector_connection(
                connector_id, settings
            )

            response_time = int(
                (time.time() - start_time) * 1000
            )  # Convert to milliseconds

            return {
                "is_healthy": connection_result["is_connected"],
                "connection_type": connector_id,
                "errors": [connection_result["error"]]
                if connection_result["error"]
                else [],
                "response_time_ms": response_time,
            }

        except Exception as e:
            return {
                "is_healthy": False,
                "connection_type": source_config.get("connector_id", "unknown"),
                "errors": [str(e)],
                "response_time_ms": None,
            }
