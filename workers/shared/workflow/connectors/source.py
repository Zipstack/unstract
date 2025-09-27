"""Unified Source Connector for Workers

This module provides a worker-compatible implementation of the SourceConnector
that matches the exact logic from backend/workflow_manager/endpoint_v2/source.py
"""

import logging
from typing import Any

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.core.data_models import (
    ConnectorInstanceData,
    FileHashData,
    FileOperationConstants,
    SourceConnectionType,
    SourceKey,
    WorkflowEndpointConfigData,
    WorkflowEndpointConfigResponseData,
)
from unstract.core.file_operations import FileOperations

from ...api.internal_client import InternalAPIClient
from ...enums.file_types import FileProcessingOrder
from .utils import get_connector_instance

logger = logging.getLogger(__name__)


class WorkerSourceConnector:
    """Worker-compatible source connector matching backend source.py logic exactly.

    This class provides the same file listing functionality as the backend
    SourceConnector but adapted for worker processes that communicate via
    internal APIs rather than direct database access.
    """

    READ_CHUNK_SIZE = FileOperationConstants.READ_CHUNK_SIZE

    def __init__(
        self,
        api_client: InternalAPIClient,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        use_file_history: bool = False,
    ):
        """Initialize the worker source connector.

        Args:
            api_client: Internal API client for backend communication
            workflow_id: Workflow ID
            execution_id: Execution ID
            organization_id: Organization ID
            use_file_history: Whether to use file history for deduplication
        """
        self.api_client = api_client
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.use_file_history = use_file_history
        self.logger = logger

        # Get workflow endpoint configuration via API
        self.endpoint_config: WorkflowEndpointConfigData | None = (
            self._get_endpoint_configuration()
        )
        self.is_api: bool = self._is_api()

    def _is_api(self) -> bool:
        """Check if the source connector is an API connector."""
        if self.endpoint_config:
            return self.endpoint_config.connection_type == SourceConnectionType.API
        return False

    def _get_endpoint_configuration(self) -> WorkflowEndpointConfigData | None:
        """Get workflow endpoint configuration from backend."""
        try:
            workflow_endpoint_config: WorkflowEndpointConfigResponseData = (
                self.api_client.get_workflow_endpoints(
                    workflow_id=self.workflow_id,
                    organization_id=self.organization_id,
                )
            )
            return workflow_endpoint_config.source_endpoint
        except Exception as e:
            logger.error(f"Failed to get endpoint configuration: {e}")
            raise

    def list_files_from_source(
        self, file_hashes: dict[str, FileHashData] | None = None
    ) -> tuple[dict[str, FileHashData], int]:
        """List files from source connector matching backend source.py:721.

        Args:
            file_hashes: Optional existing file hashes for API workflows

        Returns:
            tuple: (matched_files, total_count)
        """
        connection_type = self.endpoint_config.connection_type

        if connection_type == SourceConnectionType.FILESYSTEM:
            files, count = self.list_files_from_file_connector()
        elif connection_type == SourceConnectionType.API:
            files, count = self.list_files_from_api_storage(file_hashes or {})
        else:
            raise ValueError(f"Invalid source connection type: {connection_type}")

        # Number files (matching backend source.py:740)
        for index, file_hash in enumerate(files.values(), start=1):
            file_hash.file_number = index

        return files, count

    def list_files_from_file_connector(self) -> tuple[dict[str, FileHashData], int]:
        """List files from filesystem connector using streaming discovery.

        This method now uses the new StreamingFileDiscovery system that:
        1. Applies all filters during discovery (not after)
        2. Stops immediately when limit is reached
        3. Uses batch processing for efficiency

        Returns:
            tuple: (matched_files, total_count)
        """
        # Get connector configuration
        connector_config: ConnectorInstanceData | None = (
            self.endpoint_config.connector_instance
        )
        connector_id = connector_config.connector_id if connector_config else None
        connector_settings = (
            connector_config.connector_metadata if connector_config else None
        )

        # Get source configuration using unified SourceKey helper methods
        source_config = self.endpoint_config.configuration if self.endpoint_config else {}
        required_patterns = SourceKey.get_file_extensions(source_config)
        recursive = SourceKey.get_process_sub_directories(source_config)
        limit = SourceKey.get_max_files(
            source_config, FileOperationConstants.DEFAULT_MAX_FILES
        )
        # Get file processing order (matching backend source.py:175)
        file_processing_order = FileProcessingOrder.from_value(
            SourceKey.get_file_processing_order(source_config)
        )
        root_dir_path = connector_settings.get("path", "")
        folders_to_process = SourceKey.get_folders(source_config)

        logger.info(
            f"Source connector configuration - Connector ID: {connector_id}, Root path: '{root_dir_path}', Folders: {folders_to_process}"
        )
        logger.info(
            f"File processing limits - Max files: {limit}, Recursive: {recursive}, Patterns: {required_patterns}"
        )
        logger.debug(f"Raw source_config for max_files debug: {source_config}")

        # Process from root if folder list is empty
        if not folders_to_process:
            folders_to_process = ["/"]

        # Get valid patterns
        patterns = FileOperations.valid_file_patterns(required_patterns)

        logger.info(
            f"Matching for patterns '{', '.join(patterns)}' from "
            f"'{', '.join(folders_to_process)}'"
        )

        # Get filesystem connector
        source_fs = self._get_fs_connector(
            settings=connector_settings, connector_id=connector_id
        )
        source_fs_fsspec = source_fs.get_fsspec_fs()

        # Validate directories
        valid_directories = []
        for input_directory in folders_to_process:
            try:
                # Use connector's root dir resolution (all connectors have this method)
                resolved_directory = source_fs.get_connector_root_dir(
                    input_dir=input_directory, root_path=root_dir_path
                )

                logger.info(
                    f"[exec:{self.execution_id}] Checking directory: '{input_directory}' → '{resolved_directory}'"
                )

                # Use connector-specific directory check instead of generic fsspec.isdir()
                # This is especially important for GCS where fsspec.isdir() doesn't work correctly
                is_directory = False
                try:
                    if hasattr(source_fs, "is_dir_by_metadata"):
                        # Get directory info and check using connector's method
                        dir_info = source_fs_fsspec.info(resolved_directory)
                        is_directory = source_fs.is_dir_by_metadata(dir_info)
                    else:
                        # Fallback to fsspec's isdir for other connectors
                        is_directory = source_fs_fsspec.isdir(resolved_directory)
                except Exception as dir_check_error:
                    logger.warning(
                        f"[exec:{self.execution_id}] Failed to check if '{resolved_directory}' is directory: {dir_check_error}"
                    )
                    is_directory = False

                if not is_directory:
                    logger.warning(
                        f"[exec:{self.execution_id}] Source directory not found or not accessible: '{resolved_directory}'. "
                        f"This may be expected if the directory doesn't exist in the connector storage."
                    )
                    continue

                valid_directories.append(resolved_directory)
                logger.info(
                    f"[exec:{self.execution_id}] ✓ Validated directory: '{resolved_directory}'"
                )

            except Exception as e:
                logger.error(
                    f"[exec:{self.execution_id}] Error accessing directory '{input_directory}': {e}"
                )
                continue

        # Choose processing strategy based on file_processing_order (matching backend source.py:215-231)
        if not valid_directories:
            logger.warning("No valid directories found to process")
            return {}, 0

        if file_processing_order == FileProcessingOrder.UNORDERED:
            # Use existing StreamingFileDiscovery for unordered processing
            logger.info(
                f"[exec:{self.execution_id}] Starting unordered streaming file discovery for {len(valid_directories)} directories"
            )
            matched_files, total_count = self._process_without_sorting(
                source_fs=source_fs,
                valid_directories=valid_directories,
                patterns=patterns,
                recursive=recursive,
                limit=limit,
            )
        else:
            # Use new sorting-based processing for OLDEST_FIRST/NEWEST_FIRST
            logger.info(
                f"[exec:{self.execution_id}] Starting ordered file processing ({file_processing_order.value}) for {len(valid_directories)} directories"
            )
            matched_files, total_count = self._process_with_sorting(
                source_fs=source_fs,
                valid_directories=valid_directories,
                patterns=patterns,
                recursive=recursive,
                limit=limit,
                file_processing_order=file_processing_order,
            )

        logger.info(
            f"[exec:{self.execution_id}] Streaming discovery complete: {total_count} files found "
            f"(limit was {limit})"
        )

        return matched_files, total_count

    # NOTE: The old _get_matched_files method has been removed and replaced with
    # StreamingFileDiscovery which applies all filters during discovery, not after.
    # This eliminates duplicate filtering and improves performance significantly.

    def get_max_files_limit(self) -> int:
        """Get the max files limit from source configuration.

        Returns:
            Maximum number of files to process
        """
        source_config = self.endpoint_config.configuration if self.endpoint_config else {}
        return SourceKey.get_max_files(
            source_config, FileOperationConstants.DEFAULT_MAX_FILES
        )

    def list_files_from_api_storage(
        self, existing_file_hashes: dict[str, FileHashData]
    ) -> tuple[dict[str, FileHashData], int]:
        """List files from API storage.

        For API workflows, files are already uploaded and we just process them.
        NOTE: File history filtering is NOT applied here for API workflows as they
        have different processing patterns than ETL/TASK workflows.

        Args:
            existing_file_hashes: Pre-uploaded files

        Returns:
            tuple: (files, count)
        """
        logger.info(f"Listing {len(existing_file_hashes)} files from API storage")

        # API workflows handle filtering differently - they don't use file history
        # or active file filtering in the same way as ETL/TASK workflows
        return existing_file_hashes, len(existing_file_hashes)

    def _get_existing_file_executions_optimized(
        self, provider_file_uuids: list[str]
    ) -> dict[str, str]:
        """Check specific files against active executions in single API call.

        Instead of:
        1. Get ALL PENDING/EXECUTING executions (100+ executions)
        2. For each execution, get file executions (100+ API calls)
        3. Build massive lookup table

        Do this:
        1. Single API call to check specific files
        2. Return only files that are actively being processed

        Args:
            provider_file_uuids: List of file UUIDs to check

        Returns:
            dict: Mapping of provider_file_uuid to status for files being processed
        """
        if not provider_file_uuids:
            return {}

        try:
            if not self.workflow_id:
                return {}

            # Single optimized API call
            response = self.api_client.check_files_active_processing(
                workflow_id=self.workflow_id,
                provider_file_uuids=provider_file_uuids,
                current_execution_id=self.execution_id,
            )

            if not response.success:
                logger.warning(
                    f"Failed to check files active processing: {response.error}"
                )
                return {}

            active_data = response.data or {}
            active_uuids = active_data.get("active_uuids", [])

            if not active_uuids:
                return {}

            # Convert to expected format
            result = {}
            for uuid in active_uuids:
                result[uuid] = "PENDING_OR_EXECUTING"  # Status for filtering

            return result

        except Exception as e:
            logger.warning(f"Error in optimized file execution check: {e}")
            # Fallback to empty dict (assume no conflicts) to avoid blocking workflow
            return {}

    def _get_existing_file_executions(self) -> dict[str, str]:
        """Get existing file executions for ALL active workflow executions.

        This mimics the backend logic from source.py exactly:
        1. Get ALL active executions for the workflow (PENDING/EXECUTING status)
        2. For each active execution, get file executions
        3. Skip files that are being processed in ANY active execution

        This prevents race conditions between concurrent executions of the same workflow.

        Returns:
            dict: Mapping of provider_file_uuid to execution status
        """
        try:
            if not self.workflow_id:
                return {}

            from unstract.core.data_models import ExecutionStatus

            # Step 1: Get ALL active workflow executions (matching backend _get_active_workflow_executions)
            try:
                # Get workflow executions with PENDING or EXECUTING status
                workflow_response = self.api_client.get_workflow_executions_by_status(
                    workflow_id=self.workflow_id,
                    statuses=[
                        ExecutionStatus.PENDING.value,
                        ExecutionStatus.EXECUTING.value,
                    ],
                )

                if not workflow_response.success:
                    logger.warning(
                        f"Failed to get active workflow executions: {workflow_response.error}"
                    )
                    return {}

                active_executions = workflow_response.data or []

                if not active_executions:
                    logger.info(
                        f"No active executions found for workflow {self.workflow_id}"
                    )
                    return {}

                logger.info(
                    f"Found {len(active_executions)} active executions for workflow {self.workflow_id}"
                )

            except Exception as workflow_error:
                logger.warning(
                    f"Error getting active workflow executions: {workflow_error}"
                )
                return {}

            # Step 2: For each active execution, get file executions (matching backend loop)
            all_file_executions = {}

            for execution_data in active_executions:
                execution_id = execution_data.get("id")
                execution_status = execution_data.get("status")

                if not execution_id:
                    continue

                logger.info(
                    f"Checking file executions for execution {execution_id} (status: {execution_status})"
                )

                try:
                    # Get file executions for this specific execution
                    response = self.api_client.get_workflow_file_executions_by_execution(
                        execution_id
                    )

                    if not response.success:
                        logger.warning(
                            f"Failed to get file executions for {execution_id}: {response.error}"
                        )
                        continue

                    file_executions_data = response.data or []

                except Exception as api_error:
                    logger.warning(
                        f"Error getting file executions for {execution_id}: {api_error}"
                    )
                    continue

                # Process file executions for this execution
                if file_executions_data and isinstance(file_executions_data, list):
                    skip_statuses = ExecutionStatus.get_skip_processing_statuses()
                    skip_status_values = [status.value for status in skip_statuses]

                    for file_exec in file_executions_data:
                        provider_uuid = file_exec.get("provider_file_uuid")
                        status = file_exec.get("status")
                        file_name = file_exec.get("file_name", "unknown")
                        file_path = file_exec.get("file_path", "")

                        # Only include files that should be skipped (matching backend logic)
                        if provider_uuid and status and status in skip_status_values:
                            # Keep track of which execution is blocking this file
                            all_file_executions[provider_uuid] = {
                                "status": status,
                                "execution_id": execution_id,
                                "file_name": file_name,
                                "file_path": file_path,
                            }

            # Convert to the expected format (provider_uuid -> status)
            file_executions = {
                uuid: data["status"] for uuid, data in all_file_executions.items()
            }

            if file_executions:
                logger.info(
                    f"Found {len(file_executions)} existing file executions to skip across {len(active_executions)} active executions "
                    f"(PENDING: {sum(1 for s in file_executions.values() if s == ExecutionStatus.PENDING.value)}, "
                    f"EXECUTING: {sum(1 for s in file_executions.values() if s == ExecutionStatus.EXECUTING.value)}, "
                    f"COMPLETED: {sum(1 for s in file_executions.values() if s == ExecutionStatus.COMPLETED.value)})"
                )
            else:
                logger.info(
                    f"No blocking file executions found across {len(active_executions)} active workflow executions. "
                    f"This is normal when no files are currently being processed."
                )

            return file_executions

        except Exception as e:
            logger.warning(f"Error getting existing file executions: {e}")
            # Return empty dict to allow processing to continue
            return {}

    # NOTE: The _apply_file_history_filtering method has been removed.
    # File history filtering is now handled by the FileHistoryFilter in FilterPipeline
    # during streaming discovery, eliminating duplicate API calls.

    def _get_fs_connector(
        self, settings: dict[str, Any], connector_id: str
    ) -> UnstractFileSystem:
        """Get filesystem connector instance.

        Args:
            settings: Connector settings
            connector_id: Connector ID

        Returns:
            UnstractFileSystem: Connector instance
        """
        return get_connector_instance(connector_id, settings)

    def get_file_content_hash(self, source_fs: UnstractFileSystem, file_path: str) -> str:
        """Get file content hash matching backend source.py:745.

        Args:
            source_fs: Filesystem connector
            file_path: Path to file

        Returns:
            str: SHA256 hash of file content
        """
        return FileOperations.compute_file_content_hash_from_fsspec(source_fs, file_path)

    def _process_without_sorting(
        self,
        source_fs: UnstractFileSystem,
        valid_directories: list[str],
        patterns: list[str],
        recursive: bool,
        limit: int,
    ) -> tuple[dict[str, FileHashData], int]:
        """Process files without ordering using StreamingFileDiscovery (existing logic).

        This method wraps the existing StreamingFileDiscovery logic to maintain
        compatibility with unordered processing while allowing ordered processing
        via the new _process_with_sorting method.
        """
        # Import from shared processing module - no circular dependency
        from ...processing.file_discovery import StreamingFileDiscovery
        from ...processing.filter_pipeline import create_standard_pipeline

        # Create the streaming discovery instance
        streaming_discovery = StreamingFileDiscovery(
            source_fs=source_fs,
            api_client=self.api_client,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            organization_id=self.organization_id,
            connector_id=None,  # Set to None if not available
        )

        # Create filter pipeline with all filters applied during discovery
        # File history and active file filtering are now done during discovery, not after
        filter_pipeline = create_standard_pipeline(
            use_file_history=self.use_file_history,
            enable_active_filtering=True,  # Always enable for ETL/TASK workflows
        )

        # Discover files with streaming and early filtering
        matched_files, total_count = streaming_discovery.discover_files_streaming(
            directories=valid_directories,
            patterns=patterns,
            recursive=recursive,
            file_hard_limit=limit,  # Hard limit - will stop when reached
            filter_pipeline=filter_pipeline,
            batch_size=100,  # Process files in batches of 100
        )

        return matched_files, total_count

    def _process_with_sorting(
        self,
        source_fs: UnstractFileSystem,
        valid_directories: list[str],
        patterns: list[str],
        recursive: bool,
        limit: int,
        file_processing_order: FileProcessingOrder,
    ) -> tuple[dict[str, FileHashData], int]:
        """Process files with ordering using OrderedFileDiscovery.

        This method delegates to OrderedFileDiscovery for clean architecture separation.

        Args:
            source_fs: Filesystem connector
            valid_directories: List of validated directories to process
            patterns: File patterns to match
            recursive: Whether to search recursively
            limit: Maximum number of files to return
            file_processing_order: Order to process files (OLDEST_FIRST or NEWEST_FIRST)

        Returns:
            tuple: (matched_files_dict, total_count)
        """
        # Lazy import to avoid circular dependencies
        from ...processing.file_discovery import OrderedFileDiscovery

        # Create ordered file discovery instance
        ordered_discovery = OrderedFileDiscovery(
            source_fs=source_fs,
            api_client=self.api_client,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            organization_id=self.organization_id,
            use_file_history=self.use_file_history,
            connector_id=None,  # Set to None if not available
        )

        # Discover files with ordering and chunked filtering
        return ordered_discovery.discover_files_ordered(
            directories=valid_directories,
            patterns=patterns,
            recursive=recursive,
            file_hard_limit=limit,
            file_processing_order=file_processing_order.value,  # Convert enum to string
            batch_size=100,  # Process in batches of 100 files
        )
