"""File Storage Client for Look-Up reference data.

This module provides integration with Unstract's file storage
for loading extracted reference data content.
"""

import logging

from utils.file_storage.constants import FileStorageKeys

from unstract.sdk1.file_storage.constants import StorageType
from unstract.sdk1.file_storage.env_helper import EnvHelper

logger = logging.getLogger(__name__)


class FileStorageClient:
    """Storage client implementation using Unstract's file storage.

    This client uses the actual platform file storage to read
    extracted reference data content.
    """

    def __init__(self):
        """Initialize the file storage client."""
        self.fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )

    def get(self, path: str) -> str:
        """Retrieve file content from storage.

        Args:
            path: Storage path to the file

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
            Exception: If reading fails
        """
        try:
            if not self.fs_instance.exists(path):
                logger.error(f"File not found: {path}")
                raise FileNotFoundError(f"File not found: {path}")

            # Use read() method with text mode
            content = self.fs_instance.read(path, mode="r", encoding="utf-8")
            logger.debug(f"Read {len(content)} chars from {path}")
            return content

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to read file {path}: {e}")
            raise Exception(f"Failed to read file: {str(e)}")

    def exists(self, path: str) -> bool:
        """Check if path exists in storage.

        Args:
            path: Storage path

        Returns:
            True if exists
        """
        return self.fs_instance.exists(path)

    def get_text_content(self, path: str) -> str | None:
        """Get text content from storage (alias for get).

        Args:
            path: Storage path

        Returns:
            Text content or None if not found
        """
        try:
            return self.get(path)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Error reading {path}: {e}")
            return None
