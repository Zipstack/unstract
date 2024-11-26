import logging
import os
from typing import Any

from unstract.sdk.file_storage import FileStorageProvider
from unstract.sdk.file_storage.fs_impl import FileStorage
from unstract.sdk.file_storage.fs_permanent import PermanentFileStorage

from unstract.filesystem.file_storage_types import FileStorageType

from .file_storage_config import (
    FILE_STORAGE_CREDENTIALS_MAPPING,
    FILE_STORAGE_PROVIDER_MAPPING,
    STORAGE_MAPPING,
)

logger = logging.getLogger(__name__)


class FileSystem:
    def __init__(self, file_storage_type: FileStorageType):
        self.file_storage_type = file_storage_type

    def _get_credentials(self) -> dict[str, Any]:
        """Retrieve storage credentials based on the storage type."""
        return FILE_STORAGE_CREDENTIALS_MAPPING.get(self.file_storage_type, {})

    def _get_provider(self) -> FileStorageProvider:
        """Retrieve provider based on the storage type."""
        provider_name = FILE_STORAGE_PROVIDER_MAPPING.get(self.file_storage_type)
        if not provider_name:
            raise ValueError(f"No provider found for {self.file_storage_type}.")
        return provider_name

    def get_file_storage(self) -> FileStorage:
        """Initialize and return the appropriate file storage instance."""
        # Get the storage class based on the FileStorageType
        storage_class = STORAGE_MAPPING.get(self.file_storage_type)

        if not storage_class:
            raise ValueError(f"Unsupported FileStorageType: {self.file_storage_type}")

        # Base configuration for all storage classes
        credentials = self._get_credentials()

        # Add specific parameters based on the storage class type
        if storage_class == PermanentFileStorage:
            credentials["legacy_storage_path"] = os.getenv("LEGACY_STORAGE_PATH", None)

        # Return an instance of the storage class with the appropriate configuration
        return storage_class(provider=self._get_provider(), **credentials)
