"""Connector interfaces following Interface Segregation Principle.

These interfaces define contracts for different types of connectors,
allowing for flexible connector implementations.
"""

from abc import ABC, abstractmethod
from typing import Any


class ConnectorInterface(ABC):
    """Base interface for all connectors."""

    @abstractmethod
    def validate_configuration(self, config: dict[str, Any]) -> bool:
        """Validate connector configuration."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connector connection."""
        pass

    @abstractmethod
    def get_connection_info(self) -> dict[str, Any]:
        """Get connector connection information."""
        pass


class SourceConnectorInterface(ConnectorInterface):
    """Interface for source connectors (read data)."""

    @abstractmethod
    def list_files(self, path: str | None = None) -> list[dict[str, Any]]:
        """List files from source."""
        pass

    @abstractmethod
    def read_file(self, file_path: str) -> bytes:
        """Read file content from source."""
        pass

    @abstractmethod
    def get_file_metadata(self, file_path: str) -> dict[str, Any]:
        """Get file metadata from source."""
        pass


class DestinationConnectorInterface(ConnectorInterface):
    """Interface for destination connectors (write data)."""

    @abstractmethod
    def write_file(self, file_path: str, content: bytes) -> bool:
        """Write file content to destination."""
        pass

    @abstractmethod
    def create_directory(self, directory_path: str) -> bool:
        """Create directory at destination."""
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> bool:
        """Delete file from destination."""
        pass


class DatabaseConnectorInterface(ConnectorInterface):
    """Interface for database connectors."""

    @abstractmethod
    def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute database query."""
        pass

    @abstractmethod
    def insert_records(self, table_name: str, records: list[dict[str, Any]]) -> bool:
        """Insert records into database table."""
        pass

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """Get database schema information."""
        pass
