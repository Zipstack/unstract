"""Unified Connection Types for Unstract Platform

This module provides a centralized definition of connection types used across
the entire Unstract platform to ensure consistency and prevent duplication.
"""

from enum import Enum


class ConnectionType(str, Enum):
    """Core connection types for workflow endpoints and connectors.

    This enum provides the fundamental connection types used across:
    - workers/shared/enums.py
    - workers/shared/workflow/source_connector.py
    - workers/shared/workflow/destination_connector.py
    - unstract/core/src/unstract/core/data_models.py
    - unstract/core/src/unstract/core/workflow_utils.py
    """

    FILESYSTEM = "FILESYSTEM"
    DATABASE = "DATABASE"
    API = "API"
    MANUALREVIEW = "MANUALREVIEW"

    def __str__(self):
        return self.value

    @property
    def is_filesystem(self) -> bool:
        """Check if this is a filesystem connection type."""
        return self == ConnectionType.FILESYSTEM

    @property
    def is_database(self) -> bool:
        """Check if this is a database connection type."""
        return self == ConnectionType.DATABASE

    @property
    def is_api(self) -> bool:
        """Check if this is an API connection type."""
        return self == ConnectionType.API

    @property
    def is_manual_review(self) -> bool:
        """Check if this is a manual review connection type."""
        return self == ConnectionType.MANUALREVIEW

    @classmethod
    def from_string(cls, connection_type: str) -> "ConnectionType":
        """Create ConnectionType from string, with validation.

        Args:
            connection_type: Connection type string

        Returns:
            ConnectionType enum value

        Raises:
            ValueError: If connection type is not recognized or is empty
        """
        if not connection_type:
            raise ValueError("Connection type cannot be empty")

        connection_type_upper = connection_type.upper()

        try:
            return cls(connection_type_upper)
        except ValueError:
            raise ValueError(f"Unknown connection type: {connection_type}")
