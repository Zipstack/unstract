"""This module exposes the main classes for file storage handling."""

from unstract.flags.feature_flag import check_feature_flag_status

from .file_storage_types import FileStorageType
from .filesystem import FileSystem

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.file_storage import SharedTemporaryFileStorage
else:
    from unstract.sdk.file_storage import SharedTemporaryFileStorage

__all__ = ["FileSystem", "SharedTemporaryFileStorage", "FileStorageType"]
