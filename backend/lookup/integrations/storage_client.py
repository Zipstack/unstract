"""Object Storage integration for Look-Up reference data.

This module provides integration with PERMANENT_REMOTE_STORAGE
for storing and retrieving reference data files.
"""

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from utils.file_storage.constants import FileStorageKeys

from unstract.sdk1.file_storage.constants import StorageType
from unstract.sdk1.file_storage.env_helper import EnvHelper

from ..protocols import StorageClient

logger = logging.getLogger(__name__)


class RemoteStorageClient(StorageClient):
    """Implementation of StorageClient using PERMANENT_REMOTE_STORAGE.

    This client integrates with the Unstract file storage system
    to store and retrieve Look-Up reference data.
    """

    def __init__(self, base_path: str = "lookup/reference_data"):
        """Initialize the remote storage client.

        Args:
            base_path: Base path for Look-Up data in storage
        """
        self.base_path = base_path
        self.fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )

    def _get_project_path(self, project_id: UUID) -> str:
        """Get the storage path for a project.

        Args:
            project_id: Project UUID

        Returns:
            Storage path string
        """
        return str(Path(self.base_path) / str(project_id))

    def _get_file_path(self, project_id: UUID, filename: str) -> str:
        """Get the full storage path for a file.

        Args:
            project_id: Project UUID
            filename: File name

        Returns:
            Full storage path
        """
        return str(Path(self._get_project_path(project_id)) / filename)

    def upload(self, path: str, content: bytes) -> bool:
        """Upload content to remote storage.

        Args:
            path: Storage path
            content: File content as bytes

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure parent directory exists
            parent_dir = str(Path(path).parent)
            self.fs_instance.mkdir(parent_dir, create_parents=True)

            # Write content
            self.fs_instance.write(path=path, mode="wb", data=content)
            logger.info(f"Successfully uploaded file to {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to upload file to {path}: {e}")
            return False

    def download(self, path: str) -> bytes | None:
        """Download content from remote storage.

        Args:
            path: Storage path

        Returns:
            File content as bytes or None if not found
        """
        try:
            if not self.exists(path):
                logger.warning(f"File not found at path: {path}")
                return None

            # Read content
            content = self.fs_instance.read(path=path, mode="rb")
            logger.info(f"Successfully downloaded file from {path}")
            return content

        except Exception as e:
            logger.error(f"Failed to download file from {path}: {e}")
            return None

    def delete(self, path: str) -> bool:
        """Delete content from remote storage.

        Args:
            path: Storage path

        Returns:
            True if deleted, False otherwise
        """
        try:
            if not self.exists(path):
                logger.warning(f"File not found for deletion: {path}")
                return False

            self.fs_instance.delete(path)
            logger.info(f"Successfully deleted file at {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete file at {path}: {e}")
            return False

    def exists(self, path: str) -> bool:
        """Check if path exists in storage.

        Args:
            path: Storage path

        Returns:
            True if exists, False otherwise
        """
        try:
            return self.fs_instance.exists(path)
        except Exception as e:
            logger.error(f"Failed to check existence of {path}: {e}")
            return False

    def list_files(self, prefix: str) -> list[str]:
        """List files with given prefix.

        Args:
            prefix: Path prefix

        Returns:
            List of matching paths
        """
        try:
            # List all files in the directory
            files = self.fs_instance.listdir(prefix)
            return [str(Path(prefix) / f) for f in files if not f.startswith(".")]

        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            return []

    def get_text_content(self, path: str) -> str | None:
        """Get text content from storage.

        Args:
            path: Storage path

        Returns:
            Text content or None if not found
        """
        content = self.download(path)
        if content:
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                logger.error(f"Failed to decode text content from {path}")
        return None

    def save_text_content(self, path: str, text: str) -> bool:
        """Save text content to storage.

        Args:
            path: Storage path
            text: Text content

        Returns:
            True if successful
        """
        return self.upload(path, text.encode("utf-8"))

    def upload_reference_data(
        self,
        project_id: UUID,
        filename: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Upload reference data for a Look-Up project.

        Args:
            project_id: Project UUID
            filename: Original filename
            content: File content
            metadata: Optional metadata

        Returns:
            Storage path of uploaded file
        """
        # Generate storage path
        storage_path = self._get_file_path(project_id, filename)

        # Upload file
        if self.upload(storage_path, content):
            # Store metadata if provided
            if metadata:
                meta_path = f"{storage_path}.meta.json"
                import json

                meta_content = json.dumps(metadata, indent=2)
                self.save_text_content(meta_path, meta_content)

            return storage_path
        else:
            raise Exception(f"Failed to upload reference data to {storage_path}")

    def get_reference_data(self, project_id: UUID, filename: str) -> str | None:
        """Get reference data text content.

        Args:
            project_id: Project UUID
            filename: File name

        Returns:
            Text content or None
        """
        storage_path = self._get_file_path(project_id, filename)
        return self.get_text_content(storage_path)

    def list_project_files(self, project_id: UUID) -> list[str]:
        """List all files for a project.

        Args:
            project_id: Project UUID

        Returns:
            List of file paths
        """
        project_path = self._get_project_path(project_id)
        return self.list_files(project_path)

    def delete_project_data(self, project_id: UUID) -> bool:
        """Delete all data for a project.

        Args:
            project_id: Project UUID

        Returns:
            True if successful
        """
        try:
            project_path = self._get_project_path(project_id)
            files = self.list_project_files(project_id)

            # Delete all files
            for file_path in files:
                self.delete(file_path)

            # Delete directory
            if self.exists(project_path):
                self.fs_instance.rmdir(project_path)

            logger.info(f"Deleted all data for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete project data: {e}")
            return False
