import json
from typing import Any

from django.conf import settings
from django.db import connection
from fsspec import AbstractFileSystem
from unstract.workflow_execution.execution_file_handler import (
    ExecutionFileHandler,
)
from utils.constants import Common

from unstract.connectors.filesystems import connectors
from unstract.connectors.filesystems.unstract_file_system import (
    UnstractFileSystem,
)


class BaseConnector(ExecutionFileHandler):
    """Base class for connectors providing common methods and utilities."""

    def __init__(
        self, workflow_id: str, execution_id: str, organization_id: str
    ) -> None:
        """Initialize the BaseConnector class.

        This class serves as a base for connectors and provides common
        utilities.
        """
        if not (settings.API_STORAGE_DIR and settings.WORKFLOW_DATA_DIR):
            raise ValueError("Missed env API_STORAGE_DIR or WORKFLOW_DATA_DIR")
        super().__init__(workflow_id, execution_id, organization_id)
        # Directory path for storing execution-related files for API
        self.api_storage_dir: str = self.create_execution_dir_path(
            workflow_id, execution_id, organization_id, settings.API_STORAGE_DIR
        )

    def get_fsspec(
        self, settings: dict[str, Any], connector_id: str
    ) -> AbstractFileSystem:
        """Get an fsspec file system based on the specified connector.

        Parameters:
        - settings (dict): Connector-specific settings.
        - connector_id (str): Identifier for the desired connector.

        Returns:
        AbstractFileSystem: An fsspec file system instance.

        Raises:
        KeyError: If the connector_id is not found in the connectors dictionary.
        """
        if connector_id not in connectors:
            raise ValueError(f"Invalid connector_id: {connector_id}")
        connector = connectors[connector_id][Common.METADATA][Common.CONNECTOR]
        connector_class: UnstractFileSystem = connector(settings)
        return connector_class.get_fsspec_fs()

    @classmethod
    def get_json_schema(cls, file_path: str) -> dict[str, Any]:
        """Load and return a JSON schema from the specified file path.

        Parameters:
        - file_path (str): The path to the JSON schema file.

        Returns:
        dict: The loaded JSON schema.

        Raises:
        json.JSONDecodeError: If there is an issue decoding the JSON file.
        """
        try:
            with open(file_path, encoding="utf-8") as file:
                schema: dict[str, Any] = json.load(file)
        except OSError:
            schema = {}
        return schema

    @classmethod
    def get_api_storage_dir_path(
        cls, workflow_id: str, execution_id: str
    ) -> str:
        """Get the directory path for storing api files.

        Parameters:
        - workflow_id (str): Identifier for the workflow.
        - execution_id (str): Identifier for the execution.
        - organization_id (Optional[str]): Identifier for the organization
            (default: None).

        Returns:
        str: The directory path for the execution.
        """
        organization_id = connection.tenant.schema_name
        api_storage_dir: str = cls.create_execution_dir_path(
            workflow_id, execution_id, organization_id, settings.API_STORAGE_DIR
        )
        return api_storage_dir
