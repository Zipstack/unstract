import logging

from unstract.filesystem.file_storage_types import FileStorageType
from unstract.sdk.file_storage import EnvHelper, FileStorage

from .file_storage_config import (
    FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING,
    STORAGE_MAPPING,
)

logger = logging.getLogger(__name__)


class FileSystem:
    def __init__(self, file_storage_type: FileStorageType):
        self.file_storage_type = file_storage_type

    def get_file_storage(self) -> FileStorage:
        """Initialize and return the appropriate file storage instance."""
        # Get the storage class based on the FileStorageType
        storage_type = STORAGE_MAPPING.get(self.file_storage_type)
        env_name = FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING.get(
            self.file_storage_type
        )
        file_storage = EnvHelper.get_storage(storage_type, env_name)
        return file_storage
