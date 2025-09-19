"""Source Connector for Workflow Input Handling

This module provides specialized source connector for handling workflow inputs,
extracted from the backend workflow_manager/endpoint_v2/source.py to work without Django.

Handles:
- Filesystem source input
- API source input
- Source validation
- File listing and processing
"""

from dataclasses import dataclass
from typing import Any

from unstract.core.data_models import ConnectionType as CoreConnectionType

from ..infrastructure.logging.logger import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


@dataclass
class SourceConfig:
    """Worker-compatible SourceConfig implementation."""

    connection_type: str
    settings: dict[str, Any] = None
    # Connector instance fields from backend API
    connector_id: str | None = None
    connector_settings: dict[str, Any] = None
    connector_name: str | None = None

    def __post_init__(self):
        if self.settings is None:
            self.settings = {}
        if self.connector_settings is None:
            self.connector_settings = {}

    def get_core_connection_type(self) -> CoreConnectionType:
        """Convert string connection_type to CoreConnectionType enum."""
        try:
            # Use the enum directly for consistent mapping
            connection_type_upper = self.connection_type.upper()

            # Try to get enum member by value
            for connection_type_enum in CoreConnectionType:
                if connection_type_enum.value == connection_type_upper:
                    return connection_type_enum

            # Fallback: handle legacy/unknown types
            logger.warning(
                f"Unknown connection type '{self.connection_type}', defaulting to FILESYSTEM"
            )
            return CoreConnectionType.FILESYSTEM

        except Exception as e:
            logger.error(
                f"Failed to convert connection type '{self.connection_type}' to enum: {e}"
            )
            return CoreConnectionType.FILESYSTEM

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceConfig":
        """Create SourceConfig from dictionary data."""
        return cls(
            connection_type=data.get("connection_type", ""),
            settings=data.get("settings", {}),
            connector_id=data.get("connector_id"),
            connector_settings=data.get("connector_settings", {}),
            connector_name=data.get("connector_name"),
        )


class WorkerSourceConnector:
    """Worker-compatible source connector following production patterns.

    This class replicates the functionality of backend SourceConnector
    from workflow_manager/endpoint_v2/source.py without Django dependencies.
    """

    # Local connection types for workflow source handling
    class ConnectionType:
        # Standard connection types from CoreConnectionType
        FILESYSTEM = CoreConnectionType.FILESYSTEM.value
        API = CoreConnectionType.API.value
        DATABASE = CoreConnectionType.DATABASE.value

        # Workflow-specific connection type for API execution storage
        API_STORAGE = "API_STORAGE"

    def __init__(self, config: SourceConfig, workflow_log=None):
        self.config = config
        self.connection_type = config.connection_type
        self.settings = config.settings
        self.workflow_log = workflow_log

        # Store connector instance details
        self.connector_id = config.connector_id
        self.connector_settings = config.connector_settings
        self.connector_name = config.connector_name

    @classmethod
    def from_config(cls, workflow_log, config: SourceConfig):
        """Create source connector from config (matching Django backend interface)."""
        return cls(config, workflow_log)

    def get_fsspec_fs(self):
        """Get fsspec filesystem for the source connector.

        This method replicates backend logic for getting filesystem access.
        """
        if self.connection_type == self.ConnectionType.API_STORAGE:
            # API storage uses workflow execution storage
            from unstract.filesystem import FileStorageType, FileSystem

            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            return file_system.get_file_storage()

        if not self.connector_id or not self.connector_settings:
            raise Exception("Source connector not configured")

        # Get the connector instance using connectorkit
        from unstract.connectors.connectorkit import Connectorkit

        connectorkit = Connectorkit()
        connector_class = connectorkit.get_connector_class_by_connector_id(
            self.connector_id
        )
        connector_instance = connector_class(self.connector_settings)

        # Get fsspec filesystem
        return connector_instance.get_fsspec_fs()

    def read_file_content(self, file_path: str) -> bytes:
        """Read file content from source connector.

        Args:
            file_path: Path to the file in source storage

        Returns:
            File content as bytes
        """
        fs = self.get_fsspec_fs()

        if self.connection_type == self.ConnectionType.API_STORAGE:
            # For API storage, use the filesystem's read method
            return fs.read(file_path, mode="rb")
        else:
            # For other connectors, use fsspec open
            with fs.open(file_path, "rb") as f:
                return f.read()

    def list_files(
        self, input_directory: str, file_pattern: str = None
    ) -> list[dict[str, Any]]:
        """List files from source connector.

        Args:
            input_directory: Directory to list files from
            file_pattern: Optional glob pattern to filter files

        Returns:
            List of file information dictionaries
        """
        fs = self.get_fsspec_fs()

        # Implementation would list files using fsspec
        # This is a simplified version
        try:
            files = []
            if self.connection_type == self.ConnectionType.API_STORAGE:
                # Use filesystem listing
                file_paths = fs.list(input_directory)
            else:
                # Use fsspec listing
                file_paths = fs.ls(input_directory, detail=False)

            for file_path in file_paths:
                files.append(
                    {
                        "name": file_path.split("/")[-1],
                        "path": file_path,
                    }
                )

            return files
        except Exception as e:
            logger.error(f"Failed to list files from source: {e}")
            return []

    def validate(self) -> None:
        """Validate source connector configuration."""
        connection_type = self.connection_type

        if connection_type not in [
            self.ConnectionType.FILESYSTEM,
            self.ConnectionType.API,
            self.ConnectionType.API_STORAGE,
        ]:
            raise Exception(f"Invalid source connection type: {connection_type}")

        if connection_type == self.ConnectionType.FILESYSTEM:
            if not self.connector_id or not self.connector_settings:
                raise Exception("Filesystem source requires connector configuration")

    def get_config(self) -> SourceConfig:
        """Get serializable configuration for the source connector."""
        return self.config


# Alias for backward compatibility
SourceConnector = WorkerSourceConnector
