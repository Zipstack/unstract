import json
import logging
import os
from json import JSONDecodeError
from typing import Any

from boxfs import BoxFileSystem
from boxsdk import JWTAuth
from boxsdk.exception import BoxOAuthException

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)
logging.getLogger("boxsdk").setLevel(logging.ERROR)


class BoxFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Box connector")
        settings_dict = {}
        if "box_app_settings" in settings:
            try:
                settings_dict = json.loads(settings["box_app_settings"])
                if not isinstance(settings_dict, dict):
                    raise ConnectorError(
                        "Box app settings should be a valid JSON.",
                        treat_as_user_message=True,
                    )
            except JSONDecodeError as e:
                raise ConnectorError(
                    f"Error while decoding app settings into a JSON: {e}"
                )

        try:
            oauth = JWTAuth.from_settings_dictionary(settings_dict)
            root_id = 0
            self.box_fs = BoxFileSystem(oauth=oauth, root_id=root_id)
        except ValueError as e:
            raise ConnectorError(
                f"Error initialising from Box app settings: {e}",
                treat_as_user_message=True,
            )
        except KeyError as e:
            raise ConnectorError(
                f"Expected a key {e} in the Box app settings",
                treat_as_user_message=True,
            )
        except BoxOAuthException as e:
            raise ConnectorError(
                f"Error initialising from Box app settings: {e.message}",
                treat_as_user_message=True,
            )

        # #  TODO: Remove this block once ServiceKeyAuth works, retaining it for testing
        # # Refer https://forum.box.com/t/free-developer-accounts-please-read/152/3
        # from boxsdk import Client, OAuth2
        # client_id = ""
        # client_secret = ""
        # access_token = ""
        # auth = OAuth2(
        #     client_id=client_id,
        #     client_secret=client_secret,
        #     access_token=access_token,
        # )
        # client = Client(auth)
        # self.box_fs = BoxFileSystem(
        #     client=client
        # )

    @staticmethod
    def get_id() -> str:
        return "box|4d94d237-ce4b-45d8-8f34-ddeefc37c0bf"

    @staticmethod
    def get_name() -> str:
        return "Box connector"

    @staticmethod
    def get_description() -> str:
        return "Fetch and store data to and from the Box content management system"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Box.png"

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
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_fsspec_fs(self) -> BoxFileSystem:
        return self.box_fs

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        logger.error(f"[Box] File hash not found for the metadata: {metadata}")
        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if the given path is a directory.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            bool: True if the path is a directory, False otherwise.
        """
        raise NotImplementedError

    def test_credentials(self) -> bool:
        """To test credentials for the Box connector."""
        is_dir = False
        try:
            is_dir = bool(self.get_fsspec_fs().isdir("/"))
        except Exception as e:
            raise ConnectorError(
                f"Error from Box while testing connection: {str(e)}"
            ) from e
        if not is_dir:
            raise ConnectorError(
                "Unable to connect to Box, please check the connection settings."
            )
        return True
