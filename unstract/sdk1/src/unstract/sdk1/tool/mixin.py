import logging
from typing import Any

from unstract.sdk.file_storage import FileStorage, FileStorageProvider
from unstract.sdk.utils import ToolUtils

logger = logging.getLogger(__name__)


class ToolConfigHelper:
    """Helper class to handle static commands for tools."""

    @staticmethod
    def spec(
        spec_file: str = "config/spec.json",
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> dict[str, Any]:
        """Returns the JSON schema for the tool settings.

        Args:
            spec_file (str): The path to the JSON schema file.
            The default is config/spec.json.

        Returns:
            str: The JSON schema of the tool.
        """
        return ToolUtils.load_json(spec_file, fs=fs)

    @staticmethod
    def properties(
        properties_file: str = "config/properties.json",
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> dict[str, Any]:
        """Returns the properties of the tool.

        Args:
            properties_file (str): The path to the properties file.
            The default is config/properties.json.

        Returns:
            str: The properties of the tool.
        """
        return ToolUtils.load_json(properties_file, fs)

    @staticmethod
    def variables(
        variables_file: str = "config/runtime_variables.json",
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> dict[str, Any]:
        """Returns the JSON schema of the runtime variables.

        Args:
            variables_file (str): The path to the JSON schema file.
            The default is config/runtime_variables.json.

        Returns:
            str: The JSON schema for the runtime variables.
        """
        try:
            return ToolUtils.load_json(variables_file, fs)
        # Allow runtime variables definition to be optional
        except FileNotFoundError:
            logger.info("No runtime variables defined for tool")
            return {}

    @staticmethod
    def icon(
        icon_file: str = "config/icon.svg",
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> str:
        """Returns the icon of the tool.

        Args:
            icon_file (str): The path to the icon file.
                The default is config/icon.svg.

        Returns:
            str: The icon of the tool.
        """
        icon = fs.read(path=icon_file, mode="rb", encoding="utf-8")
        return icon
