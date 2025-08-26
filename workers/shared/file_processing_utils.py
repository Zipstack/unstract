"""File Processing Utilities for Worker Tasks

This module provides standardized file processing operations, batching,
validation, and conversion utilities used across worker implementations.
"""

import math
import time
from typing import Any

from unstract.core.data_models import FileHashData

from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class FileProcessingUtils:
    """Centralized file processing operations and utilities."""

    @staticmethod
    def convert_file_hash_data(
        hash_values_of_files: dict[str, Any] | None,
    ) -> dict[str, FileHashData]:
        """Standardized file hash conversion with comprehensive error handling.

        Args:
            hash_values_of_files: Raw file hash data from API

        Returns:
            Dictionary of converted FileHashData objects

        Note:
            This consolidates the repeated file conversion logic found across
            api-deployment, general, and file_processing workers.
        """
        if not hash_values_of_files:
            logger.warning("No file hash data provided for conversion")
            return {}

        converted_files = {}
        conversion_errors = []

        for file_key, file_data in hash_values_of_files.items():
            try:
                if isinstance(file_data, dict):
                    # Convert dictionary to FileHashData
                    converted_files[file_key] = FileHashData.from_dict(file_data)

                elif isinstance(file_data, FileHashData):
                    # Already converted
                    converted_files[file_key] = file_data

                else:
                    # Attempt manual conversion for other types
                    logger.warning(
                        f"Unexpected file data type for {file_key}: {type(file_data)}. "
                        "Attempting manual conversion."
                    )
                    converted_files[file_key] = FileHashData(
                        file_name=str(file_data),
                        file_path="",  # Will be populated later
                        file_hash=file_key,
                    )

            except Exception as e:
                error_msg = f"Failed to convert file data for {file_key}: {e}"
                logger.error(error_msg)
                conversion_errors.append(error_msg)
                continue

        if conversion_errors:
            logger.warning(
                f"File conversion completed with {len(conversion_errors)} errors. "
                f"Successfully converted {len(converted_files)} files."
            )

        return converted_files

    @staticmethod
    def create_file_batches(
        files: dict[str, Any],
        organization_id: str | None = None,
        api_client=None,
        batch_size_env_var: str = "MAX_PARALLEL_FILE_BATCHES",
        default_batch_size: int = 4,
    ) -> list[list[tuple[str, Any]]]:
        """Standardized file batching algorithm used across workers with organization-specific config.

        Args:
            files: Dictionary of files to batch
            organization_id: Organization ID for configuration lookup
            api_client: Internal API client for configuration access
            batch_size_env_var: Environment variable for batch size config (fallback)
            default_batch_size: Default batch size if all else fails

        Returns:
            List of file batches, each batch is a list of (key, value) tuples

        Note:
            This consolidates the math.ceil batching logic found in
            api-deployment and general workers, now with organization-specific configuration support.
        """
        if not files:
            logger.warning("No files provided for batching")
            return []

        # Get batch size using configuration client with fallback
        from .configuration_client import get_batch_size_with_fallback

        batch_size = get_batch_size_with_fallback(
            organization_id=organization_id,
            api_client=api_client,
            env_var_name=batch_size_env_var,
            default_value=default_batch_size,  # This will be used only if passed explicitly
        )

        # Convert to list of items
        file_items = list(files.items())
        num_files = len(file_items)

        # Calculate optimal number of batches
        num_batches = min(batch_size, num_files)
        items_per_batch = math.ceil(num_files / num_batches)

        # Create batches
        batches = []
        for i in range(0, num_files, items_per_batch):
            batch = file_items[i : i + items_per_batch]
            batches.append(batch)

        logger.info(
            f"Created {len(batches)} batches from {num_files} files "
            f"(max_batch_size={batch_size}, items_per_batch={items_per_batch})"
        )

        return batches

    @staticmethod
    def validate_file_data(
        file_data: Any, operation_name: str, required_fields: list[str] | None = None
    ) -> dict[str, Any]:
        """Common file validation logic with standardized error handling.

        Args:
            file_data: File data to validate
            operation_name: Name of operation for logging context
            required_fields: List of required field names

        Returns:
            Validated file data dictionary

        Raises:
            ValueError: If validation fails

        Note:
            This consolidates validation patterns found across multiple workers.
        """
        if not file_data:
            raise ValueError(f"{operation_name}: No file data provided")

        # Convert to dict if it's a FileHashData object
        if isinstance(file_data, FileHashData):
            file_dict = file_data.__dict__
        elif isinstance(file_data, dict):
            file_dict = file_data.copy()
        else:
            raise ValueError(
                f"{operation_name}: Invalid file data type: {type(file_data)}"
            )

        # Validate required fields
        if required_fields:
            missing_fields = [
                field for field in required_fields if not file_dict.get(field)
            ]
            if missing_fields:
                raise ValueError(
                    f"{operation_name}: Missing required fields: {missing_fields}"
                )

        # Standardize file name handling
        file_name = file_dict.get("file_name")
        if not file_name or file_name == "unknown":
            logger.warning(
                f"{operation_name}: File missing or unknown name, "
                f"generating timestamp-based name"
            )
            file_dict["file_name"] = f"unknown_file_{int(time.time())}"

        # Validate execution ID
        execution_id = file_dict.get("file_execution_id")
        if not execution_id:
            logger.warning(f"{operation_name}: File missing execution ID: {file_dict}")

        return file_dict

    @staticmethod
    def extract_file_metadata(
        files: dict[str, FileHashData], include_sensitive: bool = False
    ) -> dict[str, dict[str, Any]]:
        """Extract standardized metadata from file collection.

        Args:
            files: Dictionary of FileHashData objects
            include_sensitive: Whether to include potentially sensitive data

        Returns:
            Dictionary of metadata per file

        Note:
            This provides consistent metadata extraction used in logging
            and debugging across workers.
        """
        metadata = {}

        for file_key, file_data in files.items():
            file_metadata = {
                "file_name": getattr(file_data, "file_name", "unknown"),
                "file_size": getattr(file_data, "file_size", 0),
                "file_type": getattr(file_data, "file_type", "unknown"),
                "created_at": getattr(file_data, "created_at", None),
            }

            if include_sensitive:
                file_metadata.update(
                    {
                        "file_path": getattr(file_data, "file_path", ""),
                        "file_hash": getattr(file_data, "file_hash", ""),
                    }
                )

            metadata[file_key] = file_metadata

        return metadata

    @staticmethod
    def create_file_processing_summary(
        total_files: int,
        successful_files: int,
        failed_files: int,
        skipped_files: int = 0,
        duration_seconds: float | None = None,
    ) -> str:
        """Create standardized file processing summary string.

        Args:
            total_files: Total number of files processed
            successful_files: Number of successfully processed files
            failed_files: Number of failed files
            skipped_files: Number of skipped files
            duration_seconds: Optional processing duration

        Returns:
            Formatted summary string

        Note:
            This provides consistent result reporting across all workers.
        """
        summary_parts = [
            f"total={total_files}",
            f"success={successful_files}",
            f"failed={failed_files}",
        ]

        if skipped_files > 0:
            summary_parts.append(f"skipped={skipped_files}")

        if duration_seconds is not None:
            summary_parts.append(f"duration={duration_seconds:.2f}s")

        success_rate = (successful_files / total_files * 100) if total_files > 0 else 0
        summary_parts.append(f"success_rate={success_rate:.1f}%")

        return " - ".join(summary_parts)

    @staticmethod
    def handle_file_format_variations(
        files_data: dict | list | tuple | Any,
    ) -> dict[str, Any]:
        """Handle various file data format variations found across workers.

        Args:
            files_data: File data in various possible formats

        Returns:
            Normalized dictionary format

        Note:
            This consolidates the complex file format handling found in
            file_processing worker's _process_individual_files method.
        """
        if isinstance(files_data, dict):
            return files_data

        elif isinstance(files_data, (list, tuple)):
            # Convert list/tuple to dict with index as key
            normalized = {}
            for i, item in enumerate(files_data):
                if isinstance(item, dict):
                    # Use file_name as key if available, otherwise use index
                    key = item.get("file_name", f"file_{i}")
                    normalized[key] = item
                else:
                    normalized[f"file_{i}"] = {"file_data": item}
            return normalized

        else:
            # Single item - wrap in dict
            logger.warning(
                f"Unexpected file data type: {type(files_data)}. "
                "Wrapping as single file."
            )
            return {"single_file": {"file_data": files_data}}


class FileProcessingMixin:
    """Mixin class to add file processing utilities to worker tasks."""

    def convert_files(
        self, hash_values_of_files: dict[str, Any] | None
    ) -> dict[str, FileHashData]:
        """Convert file hash data using standardized logic."""
        return FileProcessingUtils.convert_file_hash_data(hash_values_of_files)

    def create_batches(
        self, files: dict[str, Any], **kwargs
    ) -> list[list[tuple[str, Any]]]:
        """Create file batches using standardized algorithm."""
        return FileProcessingUtils.create_file_batches(files, **kwargs)

    def validate_file(
        self, file_data: Any, operation_name: str, **kwargs
    ) -> dict[str, Any]:
        """Validate file data using standardized logic."""
        return FileProcessingUtils.validate_file_data(file_data, operation_name, **kwargs)

    def create_summary(self, **kwargs) -> str:
        """Create processing summary using standardized format."""
        return FileProcessingUtils.create_file_processing_summary(**kwargs)
