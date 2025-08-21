"""Type Utilities for Workers

This module provides type checking, validation, and conversion utilities
for consistent handling of data types across all worker modules.
"""

import logging
import os
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from unstract.core.data_models import FileHash, FileHashData

logger = logging.getLogger(__name__)


class TypeConverter:
    """Utility class for type conversion and validation across workers."""

    @staticmethod
    def ensure_file_dict_format(
        input_files: dict[str, FileHashData] | list[dict] | dict[str, dict],
    ) -> dict[str, FileHashData]:
        """Convert various input formats to the standard Dict[str, FileHashData] format.

        Args:
            input_files: Files in various formats (dict, list, etc.)

        Returns:
            Dictionary with file names as keys and FileHashData objects as values

        Raises:
            TypeError: If input format is not supported
        """
        if isinstance(input_files, dict):
            # Check if values are already FileHashData objects
            if input_files and isinstance(next(iter(input_files.values())), FileHashData):
                return input_files

            # Convert dict of dicts to dict of FileHashData objects
            result = {}
            for file_name, file_data in input_files.items():
                if isinstance(file_data, dict):
                    result[file_name] = TypeConverter.dict_to_file_hash_data(file_data)
                elif isinstance(file_data, FileHashData):
                    result[file_name] = file_data
                elif isinstance(file_data, FileHash):
                    # Convert FileHash to FileHashData
                    result[file_name] = TypeConverter.file_hash_to_file_hash_data(
                        file_data
                    )
                else:
                    logger.error(
                        f"Unsupported file data type for '{file_name}': {type(file_data)}"
                    )
                    continue
            return result

        elif isinstance(input_files, list):
            # Convert list to dict format
            result = {}
            for file_data in input_files:
                if isinstance(file_data, dict):
                    file_name = file_data.get("file_name", f"file_{len(result)}")
                    # Handle duplicate file names
                    if file_name in result:
                        file_name = TypeConverter._make_unique_filename(file_name, result)
                    result[file_name] = TypeConverter.dict_to_file_hash_data(file_data)
                elif isinstance(file_data, FileHashData):
                    file_name = file_data.file_name
                    if file_name in result:
                        file_name = TypeConverter._make_unique_filename(file_name, result)
                    result[file_name] = file_data
                else:
                    logger.error(f"Unsupported file data type in list: {type(file_data)}")
                    continue
            return result

        else:
            raise TypeError(f"Unsupported input_files type: {type(input_files)}")

    @staticmethod
    def dict_to_file_hash_data(file_dict: dict[str, Any]) -> FileHashData:
        """Convert a dictionary to FileHashData object safely.

        Args:
            file_dict: Dictionary with file data

        Returns:
            FileHashData object
        """
        try:
            # Try using the from_dict method if available
            if hasattr(FileHashData, "from_dict"):
                return FileHashData.from_dict(file_dict)

            # Manual creation as fallback
            return FileHashData(
                file_name=file_dict.get("file_name", "unknown.txt"),
                file_path=file_dict.get("file_path", ""),
                file_hash=file_dict.get("file_hash", ""),
                file_size=file_dict.get("file_size", 0),
                mime_type=file_dict.get("mime_type", ""),
                provider_file_uuid=TypeConverter.serialize_uuid(
                    file_dict.get("provider_file_uuid")
                ),
                fs_metadata=file_dict.get("fs_metadata", {}),
                source_connection_type=file_dict.get("source_connection_type"),
                file_destination=file_dict.get("file_destination"),
                is_executed=file_dict.get("is_executed", False),
                file_number=file_dict.get("file_number"),
                connector_metadata=file_dict.get("connector_metadata", {}),
                connector_id=file_dict.get("connector_id"),
            )
        except Exception as e:
            logger.error(f"Failed to convert dict to FileHashData: {e}")
            # Return minimal valid FileHashData
            return FileHashData(
                file_name=file_dict.get("file_name", "unknown.txt"),
                file_path=file_dict.get("file_path", ""),
                file_hash="",
                file_size=0,
                mime_type="application/octet-stream",
                connector_metadata=file_dict.get("connector_metadata", {}),
                connector_id=file_dict.get("connector_id"),
            )

    @staticmethod
    def file_hash_to_file_hash_data(file_hash: FileHash) -> FileHashData:
        """Convert FileHash object to FileHashData object.

        Args:
            file_hash: FileHash object to convert

        Returns:
            FileHashData object with the same data
        """
        return FileHashData(
            file_name=file_hash.file_name,
            file_path=file_hash.file_path,
            file_hash=file_hash.file_hash or "",
            file_size=file_hash.file_size or 0,
            mime_type=file_hash.mime_type or "",
            provider_file_uuid=file_hash.provider_file_uuid,
            fs_metadata=file_hash.fs_metadata or {},
            source_connection_type=file_hash.source_connection_type,
            file_destination=str(file_hash.file_destination)
            if file_hash.file_destination
            else None,
            is_executed=file_hash.is_executed,
            file_number=file_hash.file_number,
            # FileHash doesn't have these fields, use defaults
            connector_metadata={},
            connector_id=None,
        )

    @staticmethod
    def serialize_uuid(uuid_value: Any) -> str | None:
        """Safely serialize UUID objects to strings.

        Args:
            uuid_value: UUID object, string, or other value

        Returns:
            String representation of UUID or None
        """
        if uuid_value is None:
            return None

        if isinstance(uuid_value, UUID):
            return str(uuid_value)

        if isinstance(uuid_value, str):
            return uuid_value

        if hasattr(uuid_value, "hex"):
            return str(uuid_value)

        # Convert other types to string
        return str(uuid_value)

    @staticmethod
    def serialize_datetime(datetime_value: Any) -> str | None:
        """Safely serialize datetime objects to ISO format strings.

        Args:
            datetime_value: datetime, date, time object, string, or other value

        Returns:
            ISO format string representation or None
        """
        if datetime_value is None:
            return None

        if isinstance(datetime_value, (datetime, date)):
            return datetime_value.isoformat()

        if isinstance(datetime_value, time):
            return datetime_value.isoformat()

        if isinstance(datetime_value, str):
            # If it's already a string, assume it's properly formatted
            return datetime_value

        # Convert other types to string
        return str(datetime_value)

    @staticmethod
    def serialize_complex_data(data: Any) -> Any:
        """Recursively serialize complex data structures to JSON-compatible format.

        Handles datetime objects, UUID objects, tuples, sets, and nested structures.

        Args:
            data: Data to serialize

        Returns:
            JSON-compatible data structure
        """
        if isinstance(data, UUID):
            return TypeConverter.serialize_uuid(data)
        elif isinstance(data, (datetime, date, time)):
            return TypeConverter.serialize_datetime(data)
        elif isinstance(data, dict):
            return {
                key: TypeConverter.serialize_complex_data(value)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [TypeConverter.serialize_complex_data(item) for item in data]
        elif isinstance(data, tuple):
            # Convert tuple to list for JSON compatibility
            return [TypeConverter.serialize_complex_data(item) for item in data]
        elif isinstance(data, set):
            # Convert set to list for JSON compatibility
            return [TypeConverter.serialize_complex_data(item) for item in data]
        else:
            return data

    @staticmethod
    def _make_unique_filename(filename: str, existing_files: dict[str, Any]) -> str:
        """Generate a unique filename by appending a counter.

        Args:
            filename: Original filename
            existing_files: Dictionary of existing files

        Returns:
            Unique filename
        """
        if filename not in existing_files:
            return filename

        base_name, ext = os.path.splitext(filename)
        counter = 1

        while f"{base_name}_{counter}{ext}" in existing_files:
            counter += 1

        unique_name = f"{base_name}_{counter}{ext}"
        logger.warning(
            f"Duplicate filename detected, renamed '{filename}' to '{unique_name}'"
        )
        return unique_name

    @staticmethod
    def validate_file_batch_format(
        files: dict[str, FileHashData] | list[dict],
    ) -> tuple[bool, str]:
        """Validate that file batch format is correct.

        Args:
            files: Files in various formats

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not files:
            return False, "Files list is empty"

        if isinstance(files, dict):
            # Check if all values are FileHashData objects
            for file_name, file_data in files.items():
                if not isinstance(file_data, (FileHashData, dict)):
                    return (
                        False,
                        f"File '{file_name}' has invalid type: {type(file_data)}",
                    )
            return True, "Valid dict format"

        elif isinstance(files, list):
            # Check if all items are dictionaries
            for i, file_data in enumerate(files):
                if not isinstance(file_data, dict):
                    return False, f"File at index {i} has invalid type: {type(file_data)}"
                if "file_name" not in file_data:
                    return False, f"File at index {i} missing 'file_name' field"
            return True, "Valid list format"

        else:
            return False, f"Unsupported files type: {type(files)}"


class FileDataValidator:
    """Validator for FileHashData objects and related data."""

    @staticmethod
    def validate_file_hash_data(file_data: FileHashData) -> tuple[bool, list[str]]:
        """Validate FileHashData object fields.

        Args:
            file_data: FileHashData object to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if not file_data.file_name:
            errors.append("file_name is required")

        if not file_data.file_path:
            errors.append("file_path is required")

        if file_data.file_size < 0:
            errors.append("file_size cannot be negative")

        # Validate mime_type if present
        if file_data.mime_type and not file_data.mime_type.strip():
            errors.append("mime_type cannot be empty string")

        # Validate fs_metadata if present
        if file_data.fs_metadata and not isinstance(file_data.fs_metadata, dict):
            errors.append("fs_metadata must be a dictionary")

        return len(errors) == 0, errors

    @staticmethod
    def validate_file_batch_data(
        files: dict[str, FileHashData],
    ) -> tuple[bool, list[str]]:
        """Validate a batch of FileHashData objects.

        Args:
            files: Dictionary of FileHashData objects

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if not files:
            errors.append("File batch is empty")
            return False, errors

        for file_name, file_data in files.items():
            if not isinstance(file_data, FileHashData):
                errors.append(f"File '{file_name}' is not a FileHashData object")
                continue

            is_valid, file_errors = FileDataValidator.validate_file_hash_data(file_data)
            if not is_valid:
                errors.extend([f"File '{file_name}': {error}" for error in file_errors])

        return len(errors) == 0, errors
