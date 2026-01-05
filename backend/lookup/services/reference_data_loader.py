"""Reference Data Loader implementation for loading and concatenating reference data.

This module provides functionality to load reference data from object storage
and concatenate multiple sources into a single text for LLM processing.
"""

from typing import Any, Protocol
from uuid import UUID

from django.db.models import QuerySet

from lookup.exceptions import ExtractionNotCompleteError
from lookup.models import LookupDataSource


class StorageClient(Protocol):
    """Protocol for object storage client abstraction.

    Any storage client implementation must provide a get() method
    that retrieves file content by path.
    """

    def get(self, path: str) -> str:
        """Retrieve file content from storage."""
        ...


class ReferenceDataLoader:
    """Loads and concatenates reference data from object storage.

    This class handles loading reference data files that have been
    extracted from uploaded documents and stored in object storage.
    It ensures all files are properly extracted before loading and
    concatenates multiple sources in the order they were uploaded.
    """

    def __init__(self, storage_client: StorageClient):
        """Initialize the reference data loader.

        Args:
            storage_client: Object storage client (abstraction).
                          Must implement the StorageClient protocol.
        """
        self.storage = storage_client

    def load_latest_for_project(self, project_id: UUID) -> dict[str, Any]:
        r"""Load latest reference data for a project.

        Retrieves the most recent version of reference data for the specified
        project. Ensures all data sources have completed extraction before
        loading and concatenating their content.

        Args:
            project_id: UUID of the Look-Up project

        Returns:
            Dictionary containing:
                - version: Version number of the reference data
                - content: Concatenated text from all files
                - files: List of metadata about source files
                - total_size: Total size in bytes

        Raises:
            ExtractionNotCompleteError: If any data source extraction is incomplete
            LookupDataSource.DoesNotExist: If no data sources found

        Example:
            >>> loader = ReferenceDataLoader(storage)
            >>> data = loader.load_latest_for_project(project_id)
            >>> print(data["version"])
            3
            >>> print(data["content"][:50])
            '=== File: vendors.csv ===\n\nSlack\nMicrosoft...'
        """
        # Get latest version data sources
        data_sources = LookupDataSource.objects.filter(
            project_id=project_id, is_latest=True
        ).order_by("created_at")

        if not data_sources.exists():
            raise LookupDataSource.DoesNotExist(
                f"No data sources found for project {project_id}"
            )

        # Validate all extractions are complete
        is_complete, failed_files = self.validate_extraction_complete(data_sources)
        if not is_complete:
            raise ExtractionNotCompleteError(failed_files)

        # Get version number from first source (all should have same version)
        version_number = data_sources.first().version_number

        # Concatenate content from all sources
        content = self.concatenate_sources(data_sources)

        # Build file metadata
        files = []
        total_size = 0
        for source in data_sources:
            files.append(
                {
                    "id": str(source.id),
                    "name": source.file_name,
                    "size": source.file_size,
                    "type": source.file_type,
                    "uploaded_at": source.created_at.isoformat(),
                }
            )
            total_size += source.file_size

        return {
            "version": version_number,
            "content": content,
            "files": files,
            "total_size": total_size,
        }

    def load_specific_version(self, project_id: UUID, version: int) -> dict[str, Any]:
        """Load specific version of reference data.

        Retrieves a specific version of reference data for the project,
        regardless of whether it's the latest version.

        Args:
            project_id: UUID of the Look-Up project
            version: Version number to load

        Returns:
            Dictionary with same structure as load_latest_for_project()

        Raises:
            ExtractionNotCompleteError: If any data source extraction is incomplete
            LookupDataSource.DoesNotExist: If version not found

        Example:
            >>> loader = ReferenceDataLoader(storage)
            >>> data = loader.load_specific_version(project_id, 2)
            >>> print(data["version"])
            2
        """
        # Get specific version data sources
        data_sources = LookupDataSource.objects.filter(
            project_id=project_id, version_number=version
        ).order_by("created_at")

        if not data_sources.exists():
            raise LookupDataSource.DoesNotExist(
                f"Version {version} not found for project {project_id}"
            )

        # Validate all extractions are complete
        is_complete, failed_files = self.validate_extraction_complete(data_sources)
        if not is_complete:
            raise ExtractionNotCompleteError(failed_files)

        # Concatenate content from all sources
        content = self.concatenate_sources(data_sources)

        # Build file metadata
        files = []
        total_size = 0
        for source in data_sources:
            files.append(
                {
                    "id": str(source.id),
                    "name": source.file_name,
                    "size": source.file_size,
                    "type": source.file_type,
                    "uploaded_at": source.created_at.isoformat(),
                }
            )
            total_size += source.file_size

        return {
            "version": version,
            "content": content,
            "files": files,
            "total_size": total_size,
        }

    def concatenate_sources(self, data_sources: QuerySet) -> str:
        """Concatenate extracted content from multiple sources in upload order.

        Loads the extracted content for each data source from object storage
        and concatenates them with file headers for clarity.

        Args:
            data_sources: QuerySet of LookupDataSource objects,
                         should be ordered by created_at

        Returns:
            Concatenated string with all file contents separated by headers

        Example:
            >>> content = loader.concatenate_sources(sources)
            >>> print(content)
            === File: vendors.csv ===

            Slack
            Microsoft
            Google

            === File: products.txt ===

            Slack Workspace
            Microsoft Teams
        """
        contents = []

        for source in data_sources:
            # Add file header
            header = f"=== File: {source.file_name} ==="

            # Load content from storage
            # First try extracted_content_path, then fall back to original file_path
            # for text-based files (CSV, TXT, JSON)
            content_path = source.extracted_content_path
            if not content_path:
                # For text files, use the original file path
                text_file_types = ["csv", "txt", "json"]
                if source.file_type in text_file_types:
                    content_path = source.file_path

            if content_path:
                try:
                    file_content = self.storage.get(content_path)
                except Exception as e:
                    # If storage fails, include error in output
                    file_content = f"[Error loading file: {str(e)}]"
            else:
                file_content = "[No content path available]"

            # Combine header and content
            contents.append(f"{header}\n\n{file_content}")

        # Join all contents with double newline separator
        return "\n\n".join(contents)

    def validate_extraction_complete(
        self, data_sources: QuerySet
    ) -> tuple[bool, list[str]]:
        """Check if all sources have completed extraction.

        Verifies that all data sources in the queryset have successfully
        completed the extraction process.

        Args:
            data_sources: QuerySet of LookupDataSource objects

        Returns:
            Tuple of:
                - all_complete: True if all extractions complete, False otherwise
                - failed_files: List of filenames that are not complete

        Example:
            >>> is_complete, failed = loader.validate_extraction_complete(sources)
            >>> if not is_complete:
            ...     print(f"Waiting for: {', '.join(failed)}")
        """
        failed_files = []

        for source in data_sources:
            if source.extraction_status != "completed":
                failed_files.append(source.file_name)

        all_complete = len(failed_files) == 0
        return all_complete, failed_files
