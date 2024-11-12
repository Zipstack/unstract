"""
This module exposes the main classes for file storage handling.
"""

from unstract.sdk.file_storage.fs_shared_temporary import SharedTemporaryFileStorage

from .file_storage_types import FileStorageType
from .filesystem import FileSystem

__all__ = ["FileSystem", "SharedTemporaryFileStorage", "FileStorageType"]
