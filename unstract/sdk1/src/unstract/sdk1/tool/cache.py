from typing import Any

import requests
from unstract.sdk1.constants import LogLevel
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool


class ToolCache(PlatformHelper):
    """Class to handle caching for Unstract Tools.

    Notes:
        - PLATFORM_SERVICE_API_KEY environment variable is required.
    """

    def __init__(self, tool: BaseTool, platform_host: str, platform_port: int) -> None:
        """Args:
            tool (AbstractTool): Instance of AbstractTool
            platform_host (str): The host of the platform.
            platform_port (int): The port of the platform.

        Notes:
            - PLATFORM_SERVICE_API_KEY environment variable is required.
            - The platform_host and platform_port are the host and port of
                the platform service.
        """
        super().__init__(
            tool=tool, platform_host=platform_host, platform_port=platform_port
        )

    def set(self, key: str, value: str) -> bool:
        """Sets the value for a key in the cache.

        Args:
            key (str): The key.
            value (str): The value.

        Returns:
            bool: Whether the operation was successful.
        """
        url = f"{self.base_url}/cache"
        json = {"key": key, "value": value}
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        response = requests.post(url, json=json, headers=headers)

        if response.status_code == 200:
            self.tool.stream_log(f"Successfully cached data for key: {key}")
            return True
        else:
            self.tool.stream_log(
                f"Error while caching data for key: {key} / {response.reason}",
                level=LogLevel.ERROR,
            )
            return False

    def get(self, key: str) -> Any | None:
        """Gets the value for a key in the cache.

        Args:
            key (str): The key.

        Returns:
            str: The value.
        """
        url = f"{self.base_url}/cache?key={key}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            self.tool.stream_log(f"Successfully retrieved cached data for key: {key}")
            return response.text
        elif response.status_code == 404:
            self.tool.stream_log(f"Data not found for key: {key}", level=LogLevel.WARN)
            return None
        else:
            self.tool.stream_log(
                f"Error while retrieving cached data for key: "
                f"{key} / {response.reason}",
                level=LogLevel.ERROR,
            )
            return None

    def delete(self, key: str) -> bool:
        """Deletes the value for a key in the cache.

        Args:
            key (str): The key.

        Returns:
            bool: Whether the operation was successful.
        """
        url = f"{self.base_url}/cache?key={key}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        response = requests.delete(url, headers=headers)

        if response.status_code == 200:
            self.tool.stream_log(f"Successfully deleted cached data for key: {key}")
            return True
        else:
            self.tool.stream_log(
                "Error while deleting cached data " f"for key: {key} / {response.reason}",
                level=LogLevel.ERROR,
            )
            return False
