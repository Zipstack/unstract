"""Worker-Native Source Operations

This module provides worker-native source file operations without backend dependency.
Replaces the backend-dependent get_workflow_source_files from api_client.py.

Uses shared logic from @unstract/core/ for consistency with backend operations.
"""

import os
from typing import Any

# Import shared operations from connectors package
from unstract.connectors.operations import ConnectorOperations
from unstract.core.data_models import (
    FileHashData,
    FilePatternConfigData,
    SourceConnectorConfigData,
    SourceFileListingRequest,
)
from unstract.core.file_operations import FileOperations

from .api_client import InternalAPIClient
from .exceptions import (
    ConnectorConfigurationError,
    ConnectorConnectionError,
    ConnectorNotAvailableError,
    InvalidInputDirectory,
    InvalidSourceConfiguration,
    MissingSourceConnectionType,
    SourceConnectorNotConfigured,
    SourceFileListingError,
    UnsupportedConnectorType,
)

# Import worker infrastructure
from .logging_utils import WorkerLogger
from .retry_utils import circuit_breaker, retry

logger = WorkerLogger.get_logger(__name__)


class WorkerSourceOperations:
    """Handle all source operations within workers without backend dependency"""

    @staticmethod
    @retry(max_attempts=3, base_delay=2.0)
    @circuit_breaker(failure_threshold=5, recovery_timeout=60.0)
    def list_workflow_source_files(
        source_config: dict[str, Any],
        workflow_id: str,
        organization_id: str,
        execution_id: str | None = None,
        use_file_history: bool = True,
    ) -> list[FileHashData]:
        """List files from source connectors directly in worker.

        This replaces api_client.get_workflow_source_files() to eliminate backend load.
        Uses backend-compatible configuration processing and new data models.

        Args:
            source_config: Source connector configuration
            workflow_id: Workflow ID for context
            organization_id: Organization ID for context
            execution_id: Execution ID for logging (optional)
            use_file_history: Whether to consider file history (future enhancement)

        Returns:
            List of FileHashData objects representing source files

        Raises:
            ValueError: If source configuration is invalid
            ConnectionError: If source connector cannot connect
            RuntimeError: If file listing fails
        """
        logger.info(
            f"Listing source files for workflow {workflow_id} (org: {organization_id})"
        )

        try:
            # Parse source configuration using backend-compatible data models
            source_connector_config = WorkerSourceOperations._parse_source_config(
                source_config
            )

            # Create file pattern configuration
            file_pattern_config = FilePatternConfigData(
                raw_extensions=source_connector_config.get_file_extensions()
            )

            # Create standardized request using new data models
            request = SourceFileListingRequest(
                source_config=source_connector_config,
                workflow_id=workflow_id,
                organization_id=organization_id,
                execution_id=execution_id,
                use_file_history=use_file_history,
                max_files=source_connector_config.get_max_files(),
                recursive=source_connector_config.is_recursive(),
                file_pattern_config=file_pattern_config,
            )

            # Use enhanced connector operations with backend-compatible logic
            response = ConnectorOperations.list_files_from_source_enhanced(request)

            # Log processing results
            logger.info(
                f"Successfully listed {response.total_files} source files for workflow {workflow_id}"
            )
            if response.errors:
                logger.warning(
                    f"Encountered {len(response.errors)} errors during file listing"
                )

            # Log execution context if provided
            if execution_id:
                logger.debug(
                    f"Source file listing for execution {execution_id}: {response.total_files} files"
                )

            return response.files

        except (
            InvalidSourceConfiguration,
            MissingSourceConnectionType,
            SourceConnectorNotConfigured,
            ConnectorNotAvailableError,
            UnsupportedConnectorType,
            ConnectorConfigurationError,
            ConnectorConnectionError,
            InvalidInputDirectory,
        ) as e:
            # Re-raise worker-specific exceptions without wrapping
            logger.error(f"Source connector error for workflow {workflow_id}: {str(e)}")
            raise

        except Exception as e:
            # Unexpected errors - wrap in generic SourceFileListingError
            error_msg = f"Unexpected error listing source files for workflow {workflow_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise SourceFileListingError("unknown", error_msg) from e

    @staticmethod
    def _parse_source_config(source_config: dict[str, Any]) -> SourceConnectorConfigData:
        """Parse legacy source configuration into new data model format.

        This matches the backend source.py configuration separation logic:
        - connector_metadata: credentials, root_path (from connector instance)
        - endpoint_configuration: folders, patterns, limits (from endpoint config)
        """
        # Extract connector ID
        connector_id = source_config.get("connector_id") or source_config.get(
            "connection_type"
        )
        if not connector_id:
            raise MissingSourceConnectionType()

        # Extract settings (connector metadata - credentials, root path)
        settings = source_config.get("settings", {})
        if not settings:
            raise SourceConnectorNotConfigured(connector_id)

        # For backward compatibility with existing format, extract endpoint config from settings
        # In the future, this should come from separate endpoint configuration
        endpoint_config = {
            "folders": settings.get("folders", ["/"]),
            "fileExtensions": settings.get("fileExtensions", []),
            "maxFiles": settings.get("maxFiles", 1000),
            "processSubDirectories": settings.get("processSubDirectories", False),
        }

        # Create connector metadata (credentials, root path)
        connector_metadata = {
            k: v
            for k, v in settings.items()
            if k not in ["folders", "fileExtensions", "maxFiles", "processSubDirectories"]
        }

        return SourceConnectorConfigData(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            endpoint_configuration=endpoint_config,
            connection_type=source_config.get("connection_type", ""),
        )

    @staticmethod
    def get_workflow_source_config(
        workflow_id: str, organization_id: str, api_client: InternalAPIClient
    ) -> dict[str, Any]:
        """Get source configuration for workflow via database API.

        This is a database operation that should go through api_client.

        Args:
            workflow_id: Workflow ID
            organization_id: Organization ID
            api_client: API client for database operations

        Returns:
            Source connector configuration
        """
        try:
            print(f"===WorkflowID= {workflow_id}")
            # Get workflow definition via database API
            workflow_definition = api_client.get_workflow_definition(
                workflow_id=workflow_id, organization_id=organization_id
            )
            print(f"===WorkflowDefinition= {workflow_definition}")

            # Extract source configuration
            source_config = workflow_definition.get("source_config", {})
            workflow_type = workflow_definition.get("workflow_type", "ETL")

            # Handle workflows without source configuration (e.g., API-only workflows, DEFAULT workflows)
            if not source_config:
                if workflow_type in ["API", "APP", "DEFAULT"]:
                    logger.info(
                        f"Workflow {workflow_id} is type '{workflow_type}' with no source config - returning empty config"
                    )
                    return {}  # Return empty config for workflows without source
                else:
                    logger.warning(
                        f"Workflow {workflow_id} is type '{workflow_type}' but has no source config - returning empty config"
                    )
                    return {}  # Be liberal and return empty config for any workflow type

            logger.debug(
                f"Retrieved source config for workflow {workflow_id}: {source_config.get('connection_type', 'unknown')}"
            )
            return source_config

        except Exception as e:
            error_msg = (
                f"Failed to get source config for workflow {workflow_id}: {str(e)}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    @staticmethod
    def validate_source_files_batch(
        files: list[FileHashData], workflow_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate a batch of source files against workflow requirements.

        Args:
            files: List of FileHashData objects to validate
            workflow_config: Workflow configuration with validation rules

        Returns:
            Dictionary with validation results and statistics
        """
        validation_results = {
            "total_files": len(files),
            "valid_files": 0,
            "invalid_files": 0,
            "total_size": 0,
            "validation_errors": [],
            "file_validations": [],
        }

        for file_data in files:
            try:
                # Use shared file operations for validation
                file_validation = FileOperations.validate_file_compatibility(
                    file_data=file_data, workflow_config=workflow_config
                )

                validation_results["file_validations"].append(
                    {
                        "file_name": file_data.file_name,
                        "is_valid": file_validation["is_valid"],
                        "errors": file_validation["errors"],
                    }
                )

                if file_validation["is_valid"]:
                    validation_results["valid_files"] += 1
                    validation_results["total_size"] += file_data.file_size
                else:
                    validation_results["invalid_files"] += 1
                    validation_results["validation_errors"].extend(
                        [
                            f"{file_data.file_name}: {error}"
                            for error in file_validation["errors"]
                        ]
                    )

            except Exception as e:
                validation_results["invalid_files"] += 1
                validation_results["validation_errors"].append(
                    f"{file_data.file_name}: Validation failed - {str(e)}"
                )

        logger.info(
            f"Batch validation: {validation_results['valid_files']}/{validation_results['total_files']} "
            f"valid files, total size: {validation_results['total_size']} bytes"
        )

        return validation_results

    @staticmethod
    def compute_file_hashes_batch(
        files: list[FileHashData], compute_missing_only: bool = True
    ) -> list[FileHashData]:
        """Compute file hashes for a batch of files.

        This operation should be done in workers since it involves file I/O.

        Args:
            files: List of FileHashData objects
            compute_missing_only: Only compute hashes for files without existing hash

        Returns:
            List of FileHashData objects with computed hashes
        """
        logger.info(f"Computing file hashes for {len(files)} files")

        updated_files = []
        computed_count = 0

        for file_data in files:
            try:
                # Skip if hash already exists and we only want missing ones
                if compute_missing_only and file_data.file_hash:
                    updated_files.append(file_data)
                    continue

                # Compute hash using shared file operations
                if file_data.file_path:
                    file_data.file_hash = FileOperations.compute_file_hash(
                        file_data.file_path
                    )
                    computed_count += 1
                    logger.debug(
                        f"Computed hash for {file_data.file_name}: {file_data.file_hash[:8]}..."
                    )

                updated_files.append(file_data)

            except Exception as e:
                logger.warning(
                    f"Failed to compute hash for {file_data.file_name}: {str(e)}"
                )
                # Keep file without hash
                updated_files.append(file_data)

        logger.info(f"Computed hashes for {computed_count}/{len(files)} files")
        return updated_files

    @staticmethod
    def test_source_connection(
        source_config: dict[str, Any], organization_id: str
    ) -> dict[str, Any]:
        """Test source connector connectivity.

        Args:
            source_config: Source connector configuration
            organization_id: Organization ID for context

        Returns:
            Dictionary with connection test results
        """
        logger.info(f"Testing source connection for org {organization_id}")

        try:
            # Use shared connector operations for health check
            health_status = ConnectorOperations.get_connector_health(source_config)

            logger.info(
                f"Source connection test: {'PASSED' if health_status['is_healthy'] else 'FAILED'} "
                f"({health_status.get('response_time_ms', 0)}ms)"
            )

            return health_status

        except Exception as e:
            error_msg = f"Source connection test failed: {str(e)}"
            logger.error(error_msg)
            return {
                "is_healthy": False,
                "connection_type": source_config.get("connection_type"),
                "errors": [error_msg],
                "response_time_ms": None,
            }

    @staticmethod
    def get_source_file_metadata(
        file_path: str, source_config: dict[str, Any], compute_hash: bool = False
    ) -> FileHashData:
        """Get detailed metadata for a specific source file.

        Args:
            file_path: Path to the file in the source
            source_config: Source connector configuration
            compute_hash: Whether to compute file content hash

        Returns:
            FileHashData object with detailed metadata
        """
        try:
            # Use shared file operations for metadata creation
            file_data = FileOperations.create_file_metadata(
                file_path=file_path, compute_hash=compute_hash, include_fs_metadata=True
            )

            # Add source-specific information
            file_data.source_connection_type = source_config.get("connection_type")

            logger.debug(
                f"Retrieved metadata for {file_data.file_name}: {file_data.file_size} bytes"
            )
            return file_data

        except Exception as e:
            error_msg = f"Failed to get metadata for {file_path}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


class WorkerSourceFileProcessor:
    """Process source files for workflow execution using worker-native operations"""

    def __init__(self, api_client: InternalAPIClient):
        """Initialize processor with API client for database operations only.

        Args:
            api_client: API client for database operations
        """
        self.api_client = api_client

    def process_workflow_source_files(
        self,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        use_file_history: bool = True,
    ) -> dict[str, Any]:
        """Complete source file processing for workflow execution.

        This replaces the backend-heavy get_workflow_source_files operation
        with worker-native processing and minimal database updates.

        Args:
            workflow_id: Workflow ID
            execution_id: Execution ID
            organization_id: Organization ID
            use_file_history: Whether to use file history

        Returns:
            Dictionary with processing results
        """
        logger.info(
            f"Processing source files for workflow {workflow_id}, execution {execution_id}"
        )

        try:
            # Get source configuration via database API (legitimate database operation)
            source_config = WorkerSourceOperations.get_workflow_source_config(
                workflow_id=workflow_id,
                organization_id=organization_id,
                api_client=self.api_client,
            )

            # Handle workflows without source configuration (e.g., API-only workflows)
            if not source_config:
                logger.info(
                    f"Workflow {workflow_id} has no source configuration - returning empty file list"
                )
                source_files = []
            else:
                # List source files using worker-native operations (no backend load)
                source_files = WorkerSourceOperations.list_workflow_source_files(
                    source_config=source_config,
                    workflow_id=workflow_id,
                    organization_id=organization_id,
                    execution_id=execution_id,
                    use_file_history=use_file_history,
                )

            # Validate files using shared operations
            workflow_config = {"max_file_size": 100 * 1024 * 1024}  # Default config
            validation_results = WorkerSourceOperations.validate_source_files_batch(
                files=source_files, workflow_config=workflow_config
            )

            # Update execution status via database API (legitimate database operation)
            # Note: Using update_workflow_execution_status to track source file processing
            try:
                self.api_client.update_workflow_execution_status(
                    execution_id=execution_id,
                    status="EXECUTING",  # Keep current status
                    total_files=validation_results["total_files"],
                )
                logger.debug(
                    f"Updated execution {execution_id} with {validation_results['total_files']} source files"
                )
            except Exception as update_error:
                logger.warning(f"Failed to update execution metadata: {update_error}")
                # Continue processing even if metadata update fails

            # Convert to dictionary format expected by general worker
            # Key: file_name (str), Value: FileHashData object
            files_dict = {}
            for file_data in source_files:
                file_name = file_data.file_name
                # Handle duplicate file names by making them unique
                if file_name in files_dict:
                    base_name, ext = os.path.splitext(file_name)
                    counter = 1
                    while f"{base_name}_{counter}{ext}" in files_dict:
                        counter += 1
                    file_name = f"{base_name}_{counter}{ext}"
                    logger.warning(
                        f"Duplicate file name detected, renamed to: {file_name}"
                    )
                files_dict[file_name] = file_data

            processing_result = {
                "files": files_dict,
                "validation_results": validation_results,
                "source_config": source_config,
                "processing_summary": {
                    "total_files": len(source_files),
                    "valid_files": validation_results["valid_files"],
                    "total_size": validation_results["total_size"],
                },
            }

            logger.info(
                f"Source file processing complete: {len(source_files)} files, "
                f"{validation_results['valid_files']} valid"
            )

            return processing_result

        except Exception as e:
            error_msg = (
                f"Source file processing failed for workflow {workflow_id}: {str(e)}"
            )
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e
