"""Connector utilities for workers.

This module provides utilities for working with Unstract connectors
in worker processes.
"""

import logging
from typing import Any

from unstract.connectors.connectorkit import Connectorkit
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


def get_connector_instance(
    connector_id: str, settings: dict[str, Any]
) -> UnstractFileSystem:
    """Get a filesystem connector instance.

    Args:
        connector_id: Connector ID (e.g., "google_cloud_storage|uuid")
        settings: Connector settings/credentials

    Returns:
        UnstractFileSystem: Instantiated connector

    Raises:
        ValueError: If connector not found or instantiation fails
    """
    try:
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
