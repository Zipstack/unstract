import logging
import os
from typing import Any, Optional

import aiohttp
from fsspec.implementations.http import HTTPFileSystem

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


class HttpFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("HTTP(S)")
        # # TODO: Enforce this assertion?
        # baseURL = URL(settings["base_url"])
        # if baseURL.origin() != baseURL:
        #     raise ValueError("Only absolute URLs without path part are supported")

        client_kwargs: dict[str, Any] = {
            "base_url": settings["base_url"],
        }
        if all(settings.get(key) for key in ("username", "password")):
            basic_auth = aiohttp.BasicAuth(settings["username"], settings["password"])
            client_kwargs.update({"auth": basic_auth})
        self.http_fs = HTTPFileSystem(client_kwargs=client_kwargs)

    @staticmethod
    def get_id() -> str:
        return "http|6fdea346-86e4-4383-9a21-132db7c9a576"

    @staticmethod
    def get_name() -> str:
        return "HTTP(S) File Server"

    @staticmethod
    def get_description() -> str:
        return "Fetch data via HTTP(s)"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/HTTP.svg"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return False

    @staticmethod
    def can_read() -> bool:
        return True

    def get_fsspec_fs(self) -> HTTPFileSystem:
        return self.http_fs

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> Optional[str]:
        """
        Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        logger.error(f"[HTTP] File hash not found for the metadata: {metadata}")
        return None

    def test_credentials(self) -> bool:
        """To test credentials for HTTP(S)."""
        is_dir = False
        try:
            is_dir = bool(self.get_fsspec_fs().isdir("/"))
        except Exception as e:
            raise ConnectorError(
                f"Error while connecting to HTTP server: {str(e)}"
            ) from e
        if not is_dir:
            raise ConnectorError(
                "Unable to connect to HTTP server, "
                "please check the connection settings."
            )
        return True
