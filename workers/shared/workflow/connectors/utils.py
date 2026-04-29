"""Connector utilities for workers.

This module provides utilities for working with Unstract connectors
in worker processes.
"""

import logging
from typing import Any

from unstract.connectors.connectorkit import Connectorkit
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.filesystem import FileStorageType, FileSystem

logger = logging.getLogger(__name__)


# Connector IDs that resolve to the system-internal MinIO bucket. These are
# the same bucket the workers already reach via FileSystem(...) — going
# through connectorkit makes us load MinioFS, which used to opt out of
# fsspec's instance cache and leak boto3 sessions under load. We short-circuit
# them to the cached FileSystem path instead.
_SYSTEM_INTERNAL_CONNECTOR_IDS = {
    "pcs|b8cd25cd-4452-4d54-bd5e-e7d71459b702",  # UnstractCloudStorage
}


class _SystemFileStorageAdapter(UnstractFileSystem):
    """UnstractFileSystem-shaped wrapper around the cached FileSystem path.

    Returned in place of a connector instance for system-internal storage,
    so call sites that do `connector.get_fsspec_fs()` keep working without
    loading the leaky MinioFS code path.
    """

    def __init__(self, storage_type: FileStorageType):
        super().__init__("SystemFileStorage")
        self._file_storage = FileSystem(storage_type).get_file_storage()

    def get_fsspec_fs(self) -> Any:
        return self._file_storage.fs

    def test_credentials(self) -> bool:
        return True


def get_connector_instance(
    connector_id: str,
    settings: dict[str, Any],
    storage_type: FileStorageType = FileStorageType.WORKFLOW_EXECUTION,
) -> UnstractFileSystem:
    """Get a filesystem connector instance.

    For system-internal connector IDs (e.g., UnstractCloudStorage), returns
    an adapter backed by the cached FileSystem instance instead of loading
    the connector class. For all other connector IDs, behaves as before.

    Args:
        connector_id: Connector ID (e.g., "google_cloud_storage|uuid")
        settings: Connector settings/credentials
        storage_type: Which system storage role to use when short-circuiting

    Returns:
        UnstractFileSystem: Instantiated connector or system adapter

    Raises:
        ValueError: If connector not found or instantiation fails
    """
    try:
        if connector_id in _SYSTEM_INTERNAL_CONNECTOR_IDS:
            logger.debug(
                f"Routing system-internal connector {connector_id} through "
                f"FileSystem({storage_type.value})"
            )
            return _SystemFileStorageAdapter(storage_type)

        # Use Connectorkit to get connector class
        connectorkit = Connectorkit()
        connector_class = connectorkit.get_connector_class_by_connector_id(connector_id)

        if not connector_class:
            raise ValueError(f"Connector not found: {connector_id}")

        # Instantiate connector with settings
        connector = connector_class(settings)

        logger.info(f"Successfully instantiated connector: {connector_id}")
        return connector

    except Exception as e:
        logger.error(f"Failed to instantiate connector {connector_id}: {e}")
        raise ValueError(f"Failed to instantiate connector: {e}")


def validate_connector_settings(
    connector_id: str, settings: dict[str, Any]
) -> tuple[bool, str]:
    """Validate connector settings.

    Args:
        connector_id: Connector ID
        settings: Connector settings to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # Try to instantiate connector - if it works, settings are valid
        connector = get_connector_instance(connector_id, settings)

        # Additional validation if connector supports it
        if hasattr(connector, "validate_settings"):
            return connector.validate_settings()

        return True, ""

    except Exception as e:
        return False, str(e)


def get_connector_capabilities(connector_id: str) -> dict[str, bool]:
    """Get capabilities of a connector.

    Args:
        connector_id: Connector ID

    Returns:
        dict: Connector capabilities (can_read, can_write, etc.)
    """
    try:
        # Use Connectorkit to get connector class
        connectorkit = Connectorkit()
        connector_class = connectorkit.get_connector_class_by_connector_id(connector_id)

        if not connector_class:
            return {"error": f"Connector not found: {connector_id}"}

        return {
            "can_read": connector_class.can_read()
            if hasattr(connector_class, "can_read")
            else False,
            "can_write": connector_class.can_write()
            if hasattr(connector_class, "can_write")
            else False,
            "requires_oauth": connector_class.requires_oauth()
            if hasattr(connector_class, "requires_oauth")
            else False,
            "name": connector_class.get_name()
            if hasattr(connector_class, "get_name")
            else "Unknown",
            "description": connector_class.get_description()
            if hasattr(connector_class, "get_description")
            else "",
        }

    except Exception as e:
        logger.error(f"Failed to get connector capabilities: {e}")
        return {"error": str(e)}
