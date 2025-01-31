import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from fsspec import AbstractFileSystem

from backend.constants import FeatureFlag
from unstract.connectors.base import UnstractConnector
from unstract.connectors.enums import ConnectorMode
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
    from unstract.filesystem import FileStorageType, FileSystem

logger = logging.getLogger(__name__)


class UnstractFileSystem(UnstractConnector, ABC):
    """Abstract class for file systems."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_id() -> str:
        return ""

    @staticmethod
    def get_name() -> str:
        return ""

    @staticmethod
    def get_description() -> str:
        return ""

    @staticmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    def get_json_schema() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return False

    @staticmethod
    def can_read() -> bool:
        return False

    @staticmethod
    @abstractmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    @abstractmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    def get_connector_mode() -> ConnectorMode:
        return ConnectorMode.FILE_SYSTEM

    @abstractmethod
    def get_fsspec_fs(self) -> AbstractFileSystem:
        pass

    @abstractmethod
    def test_credentials(self) -> bool:
        """Override to test credentials for a connector."""
        pass

    @staticmethod
    def get_connector_root_dir(input_dir: str, **kwargs: Any) -> str:
        """Override to get root dir of a connector."""
        return f"{input_dir.strip('/')}/"

    def create_dir_if_not_exists(self, input_dir: str) -> None:
        """Method to create dir of a connector if not exists.

        Args:
            input_dir (str): input directory of source connector
        """
        fs_fsspec = self.get_fsspec_fs()
        is_dir = fs_fsspec.isdir(input_dir)
        if not is_dir:
            fs_fsspec.mkdir(input_dir)

    def upload_file_to_storage(self, source_path: str, destination_path: str) -> None:
        """Method to upload filepath from tool to destination connector
        directory.

        Args:
            source_path (str): local path of file to be uploaded, coming from tool
            destination_path (str): target path in the storage where the file will be
            uploaded
        """
        normalized_path = os.path.normpath(destination_path)
        destination_connector_fs = self.get_fsspec_fs()
        if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            workflow_fs = file_system.get_file_storage()
            data = workflow_fs.read(path=source_path, mode="rb")
        else:
            with open(source_path, "rb") as source_file:
                data = source_file.read()
        destination_connector_fs.write_bytes(normalized_path, data)
