"""Destination Connector for Workflow Output Handling

This module provides specialized destination connector for handling workflow outputs,
extracted from the monolithic workflow_service.py to improve maintainability.

Handles:
- Filesystem destination output
- Database destination output
- API destination output
- Manual review queue output
- Output processing and validation
"""

import ast
import base64
import json
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from shared.enums import QueueResultStatus

# Import database utils (stable path)
from shared.infrastructure.database.utils import WorkerDatabaseUtils
from shared.models.result_models import QueueResult
from shared.utils.manual_review_factory import (
    get_manual_review_service,
    has_manual_review_plugin,
)

from unstract.connectors.connectorkit import Connectorkit
from unstract.connectors.exceptions import ConnectorError
from unstract.core.data_models import ConnectionType as CoreConnectionType
from unstract.core.data_models import FileHashData
from unstract.filesystem import FileStorageType, FileSystem
from unstract.sdk.constants import ToolExecKey
from unstract.sdk.tool.mime_types import EXT_MIME_MAP
from unstract.workflow_execution.constants import (
    MetaDataKey,
    ToolMetadataKey,
    ToolOutputType,
)
from unstract.workflow_execution.execution_file_handler import (
    ExecutionFileHandler,
)

from ..enums import DestinationConfigKey
from ..infrastructure.logging import WorkerLogger
from ..infrastructure.logging.helpers import log_file_error, log_file_info
from ..utils.api_result_cache import get_api_cache_manager
from .connectors.service import WorkerConnectorService

if TYPE_CHECKING:
    from ..api_client import InternalAPIClient

logger = WorkerLogger.get_logger(__name__)


@dataclass
class HandleOutputResult:
    """Result of handle_output method."""

    output: dict[str, Any] | str | None
    metadata: dict[str, Any] | None
    connection_type: str


@dataclass
class ExecutionContext:
    """Execution context for destination processing."""

    workflow_id: str
    execution_id: str
    organization_id: str
    file_execution_id: str
    api_client: Optional["InternalAPIClient"] = None
    workflow_log: Any = None


@dataclass
class FileContext:
    """File-specific context for processing."""

    file_hash: FileHashData
    file_name: str
    input_file_path: str
    workflow: dict[str, Any]
    execution_error: str | None = None


@dataclass
class ProcessingResult:
    """Result of destination processing."""

    tool_execution_result: dict | str | None = None
    metadata: dict[str, Any] | None = None
    has_hitl: bool = False


@dataclass
class DestinationConfig:
    """Worker-compatible DestinationConfig implementation."""

    connection_type: str
    source_connection_type: str
    settings: dict[str, Any] = None
    is_api: bool = False
    use_file_history: bool = True
    # New connector instance fields from backend API
    connector_id: str | None = None
    connector_settings: dict[str, Any] = None
    connector_name: str | None = None
    # Manual review / HITL support
    hitl_queue_name: str | None = None
    # Source connector configuration for reading files
    source_connector_id: str | None = None
    source_connector_settings: dict[str, Any] = None
    file_execution_id: str | None = None

    def __post_init__(self):
        if self.settings is None:
            self.settings = {}
        if self.connector_settings is None:
            self.connector_settings = {}
        if self.source_connector_settings is None:
            self.source_connector_settings = {}
        # Determine if this is an API destination
        if self.connection_type and "api" in self.connection_type.lower():
            self.is_api = True

    def get_core_connection_type(self) -> CoreConnectionType:
        """Convert string connection_type to CoreConnectionType enum."""
        try:
            # Use the enum directly for consistent mapping
            connection_type_upper = self.connection_type.upper()

            # Try to get enum member by value
            for connection_type_enum in CoreConnectionType:
                if connection_type_enum.value == connection_type_upper:
                    return connection_type_enum

            # Fallback: handle legacy/unknown types
            logger.warning(
                f"Unknown connection type '{self.connection_type}', defaulting to DATABASE"
            )
            return CoreConnectionType.DATABASE

        except Exception as e:
            logger.error(
                f"Failed to convert connection type '{self.connection_type}' to enum: {e}"
            )
            return CoreConnectionType.DATABASE

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DestinationConfig":
        """Create DestinationConfig from dictionary data."""
        connector_instance = data.get("connector_instance", {})
        return cls(
            connection_type=data.get("connection_type", ""),
            source_connection_type=data.get("source_connection_type"),
            settings=data.get("configuration", {}),
            use_file_history=data.get("use_file_history", True),
            connector_id=connector_instance.get("connector_id"),
            connector_settings=connector_instance.get("connector_metadata", {}),
            connector_name=connector_instance.get("connector_name"),
            hitl_queue_name=data.get("hitl_queue_name"),
            source_connector_id=data.get("source_connector_id"),
            source_connector_settings=data.get("source_connector_settings", {}),
            file_execution_id=data.get("file_execution_id"),
        )


class WorkerDestinationConnector:
    """Worker-compatible destination connector following production patterns.

    This class replicates the functionality of backend DestinationConnector
    from workflow_manager/endpoint_v2/destination.py without Django dependencies.
    """

    # Use CoreConnectionType directly - no need for wrapper class

    def __init__(self, config: DestinationConfig, workflow_log=None):
        self.config = config
        self.connection_type = config.connection_type
        self.is_api = config.is_api
        self.use_file_history = config.use_file_history
        self.settings = config.settings
        self.workflow_log = workflow_log

        # Store destination connector instance details
        self.connector_id = config.connector_id
        self.connector_settings = config.connector_settings
        self.connector_name = config.connector_name

        # Store source connector instance details for file reading
        self.source_connector_id = config.source_connector_id
        self.source_connector_settings = config.source_connector_settings

        # Manual review / HITL support
        self.hitl_queue_name = config.hitl_queue_name

        # Workflow and execution context (will be set when handling output)
        self.organization_id = None
        self.workflow_id = None
        self.execution_id = None
        self.file_execution_id = None

        # Manual review service and API client (will be set when first needed)
        self.manual_review_service = None
        self._api_client = None

    @classmethod
    def from_config(cls, workflow_log, config: DestinationConfig):
        """Create destination connector from config (matching Django backend interface)."""
        return cls(config, workflow_log)

    def _ensure_manual_review_service(
        self, api_client: Optional["InternalAPIClient"] = None
    ):
        """Ensure manual review service is initialized (lazy loading)."""
        if self.manual_review_service is None and api_client is not None:
            self._api_client = api_client
            self.manual_review_service = get_manual_review_service(
                api_client, api_client.organization_id
            )
        return self.manual_review_service

    def _get_destination_display_name(self) -> str:
        """Get human-readable destination name for logging."""
        if self.connection_type == CoreConnectionType.DATABASE.value:
            # Try to get database type from settings
            if self.connector_name:
                return f"database ({self.connector_name})"
            elif self.settings and "table" in self.settings:
                return f"database table '{self.settings['table']}'"
            return "database"
        elif self.connection_type == CoreConnectionType.FILESYSTEM.value:
            if self.connector_name:
                return f"filesystem ({self.connector_name})"
            return "filesystem destination"
        elif self.connection_type == CoreConnectionType.API.value:
            if self.connector_name:
                return f"API ({self.connector_name})"
            return "API endpoint"
        elif self.connection_type == CoreConnectionType.MANUALREVIEW.value:
            return "manual review queue"
        else:
            return f"{self.connection_type} destination"

    # ========== REFACTORED HANDLE_OUTPUT HELPER METHODS ==========

    def _setup_execution_context(
        self,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        file_execution_id: str,
        api_client: Optional["InternalAPIClient"],
    ) -> ExecutionContext:
        """Setup and store execution context."""
        # Store in instance for backward compatibility with other methods
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.file_execution_id = file_execution_id

        return ExecutionContext(
            workflow_id=workflow_id,
            execution_id=execution_id,
            organization_id=organization_id,
            file_execution_id=file_execution_id,
            api_client=api_client,
            workflow_log=self.workflow_log,
        )

    def _setup_file_context(
        self,
        file_hash: FileHashData,
        workflow: dict[str, Any],
        execution_error: str | None,
    ) -> FileContext:
        """Setup file processing context."""
        return FileContext(
            file_hash=file_hash,
            file_name=file_hash.file_name,
            input_file_path=file_hash.file_path,
            workflow=workflow,
            execution_error=execution_error,
        )

    def _extract_processing_data(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext
    ) -> ProcessingResult:
        """Extract tool results and metadata for processing."""
        tool_result = None
        if not file_ctx.execution_error:
            tool_result = self.get_tool_execution_result_from_execution_context(
                workflow_id=exec_ctx.workflow_id,
                execution_id=exec_ctx.execution_id,
                file_execution_id=exec_ctx.file_execution_id,
                organization_id=exec_ctx.organization_id,
            )

        metadata = self.get_metadata()

        return ProcessingResult(tool_execution_result=tool_result, metadata=metadata)

    def _check_and_handle_hitl(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, result: ProcessingResult
    ) -> bool:
        """Check HITL requirements and push to queue if needed."""
        has_hitl = self._should_handle_hitl(
            file_name=file_ctx.file_name,
            file_hash=file_ctx.file_hash,
            workflow=file_ctx.workflow,
            api_client=exec_ctx.api_client,
            error=file_ctx.execution_error,
        )

        if has_hitl:
            self._push_data_to_queue(
                file_name=file_ctx.file_name,
                workflow=file_ctx.workflow,
                input_file_path=file_ctx.input_file_path,
                file_execution_id=exec_ctx.file_execution_id,
                tool_execution_result=result.tool_execution_result,
                api_client=exec_ctx.api_client,
            )

        return has_hitl

    def _process_destination(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, result: ProcessingResult
    ):
        """Route to appropriate destination handler."""
        handlers = {
            CoreConnectionType.API.value: self._handle_api_destination,
            CoreConnectionType.FILESYSTEM.value: self._handle_filesystem_destination,
            CoreConnectionType.DATABASE.value: self._handle_database_destination,
            CoreConnectionType.MANUALREVIEW.value: self._handle_manual_review_destination,
        }

        handler = handlers.get(self.connection_type)
        if handler:
            handler(exec_ctx, file_ctx, result)
        else:
            logger.warning(f"Unknown destination connection type: {self.connection_type}")

    def _handle_api_destination(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, result: ProcessingResult
    ):
        """Handle API destination processing."""
        log_file_info(
            exec_ctx.workflow_log,
            exec_ctx.file_execution_id,
            f"🔌 File '{file_ctx.file_name}' marked for API processing - preparing response",
        )

        self.cache_api_result(
            api_client=exec_ctx.api_client,
            file_hash=file_ctx.file_hash,
            workflow_id=exec_ctx.workflow_id,
            execution_id=exec_ctx.execution_id,
            result=result.tool_execution_result,
            file_execution_id=exec_ctx.file_execution_id,
            organization_id=exec_ctx.organization_id,
            error=file_ctx.execution_error,
            metadata=result.metadata,
        )

    def _handle_filesystem_destination(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, result: ProcessingResult
    ):
        """Handle filesystem destination processing."""
        if not result.has_hitl:
            log_file_info(
                exec_ctx.workflow_log,
                exec_ctx.file_execution_id,
                f"📤 File '{file_ctx.file_name}' marked for FILESYSTEM processing - copying to destination",
            )
            self.copy_output_to_output_directory(
                file_ctx.input_file_path, exec_ctx.file_execution_id, exec_ctx.api_client
            )
        else:
            logger.info(
                f"File '{file_ctx.file_name}' sent to HITL queue - FILESYSTEM processing will be handled after review"
            )

    def _handle_database_destination(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, result: ProcessingResult
    ):
        """Handle database destination processing."""
        if not result.has_hitl:
            log_file_info(
                exec_ctx.workflow_log,
                exec_ctx.file_execution_id,
                f"📤 File '{file_ctx.file_name}' marked for DATABASE processing - preparing to insert data",
            )
            if result.tool_execution_result:
                self.insert_into_db(
                    file_ctx.input_file_path,
                    result.tool_execution_result,
                    result.metadata,
                    exec_ctx.file_execution_id,
                    error_message=file_ctx.execution_error,
                    api_client=exec_ctx.api_client,
                )
            else:
                logger.warning(
                    f"No tool execution result found for file {file_ctx.file_name}, skipping database insertion"
                )
        else:
            logger.info(
                f"File '{file_ctx.file_name}' sent to HITL queue - DATABASE processing will be handled after review"
            )

    def _handle_manual_review_destination(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, result: ProcessingResult
    ):
        """Handle manual review destination processing."""
        log_file_info(
            exec_ctx.workflow_log,
            exec_ctx.file_execution_id,
            f"🔄 File '{file_ctx.file_name}' explicitly configured for MANUAL REVIEW - sending to queue",
        )

        if not result.has_hitl:
            self._push_data_to_queue(
                file_name=file_ctx.file_name,
                workflow=file_ctx.workflow,
                input_file_path=file_ctx.input_file_path,
                file_execution_id=exec_ctx.file_execution_id,
                tool_execution_result=result.tool_execution_result,
                api_client=exec_ctx.api_client,
            )

    def _handle_destination_error(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, error: Exception
    ):
        """Handle destination processing errors."""
        logger.error(f"Destination handle_output failed: {str(error)}")
        log_file_error(
            exec_ctx.workflow_log,
            exec_ctx.file_execution_id,
            f"❌ File '{file_ctx.file_name}' failed to send to destination: {str(error)}",
        )

    def _log_processing_success(
        self, exec_ctx: ExecutionContext, file_ctx: FileContext, has_hitl: bool
    ):
        """Log successful processing."""
        if has_hitl:
            destination_name = "HITL/MANUAL REVIEW"
        else:
            destination_name = self._get_destination_display_name()
        log_file_info(
            exec_ctx.workflow_log,
            exec_ctx.file_execution_id,
            f"✅ File '{file_ctx.file_name}' successfully sent to {destination_name}",
        )

    def cache_api_result(
        self,
        file_hash: FileHashData,
        workflow_id: str,
        execution_id: str,
        file_execution_id: str,
        organization_id: str,
        api_client: Any | None,
        # file_history: dict[str, Any] | None,
        result: dict[str, Any] | None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Cache API result using APIResultCacheManager."""
        try:
            # Calculate accurate elapsed time from workflow start time
            if metadata and MetaDataKey.WORKFLOW_START_TIME in metadata:
                workflow_start_time = metadata[MetaDataKey.WORKFLOW_START_TIME]
                current_time = time.time()
                actual_elapsed_time = current_time - workflow_start_time

                # Update total_elapsed_time with accurate measurement
                metadata[MetaDataKey.TOTAL_ELAPSED_TIME] = actual_elapsed_time

                logger.info(
                    f"TIMING: Calculated accurate elapsed time for API caching: {actual_elapsed_time:.3f}s "
                    f"(from workflow start: {workflow_start_time:.6f} to now: {current_time:.6f})"
                )

            # Use APIResultCacheManager for consistent caching behavior
            api_cache_manager = get_api_cache_manager()
            success = api_cache_manager.cache_api_result_direct(
                file_name=file_hash.file_name,
                file_execution_id=file_execution_id,
                workflow_id=workflow_id,
                execution_id=execution_id,
                result=result,
                error=error,
                organization_id=organization_id,
                metadata=metadata,
            )

            if success:
                logger.info(
                    f"Successfully cached API result for execution {execution_id}"
                )
            else:
                logger.warning(f"Failed to cache API result for execution {execution_id}")

            return success

        except Exception as e:
            logger.error(
                f"Failed to cache API result for execution {execution_id}: {str(e)}"
            )
            # Return False but don't re-raise - caching failures shouldn't stop execution
            raise

    def handle_output(
        self,
        is_success: bool,
        file_hash: FileHashData,
        # file_history: dict[str, Any] | None,
        workflow: dict[str, Any],
        file_execution_id: str = None,
        api_client: Optional["InternalAPIClient"] = None,
        workflow_id: str = None,
        execution_id: str = None,
        organization_id: str = None,
        execution_error: str = None,
    ) -> HandleOutputResult:
        """Handle the output based on the connection type.

        This refactored version uses clean architecture with context objects
        and single-responsibility methods for better maintainability.
        """
        # Setup contexts
        exec_ctx = self._setup_execution_context(
            workflow_id, execution_id, organization_id, file_execution_id, api_client
        )
        file_ctx = self._setup_file_context(file_hash, workflow, execution_error)

        # Log if HITL queue is configured (reduced debug logging)
        if self.hitl_queue_name:
            logger.debug(f"HITL queue configured: {self.hitl_queue_name}")

        # Extract processing data
        result = self._extract_processing_data(exec_ctx, file_ctx)

        # Check and handle HITL if needed
        result.has_hitl = self._check_and_handle_hitl(exec_ctx, file_ctx, result)

        # Process through appropriate destination
        try:
            self._process_destination(exec_ctx, file_ctx, result)
        except Exception as e:
            self._handle_destination_error(exec_ctx, file_ctx, e)
            raise

        # Log success
        self._log_processing_success(exec_ctx, file_ctx, result.has_hitl)

        return HandleOutputResult(
            output=result.tool_execution_result,
            metadata=result.metadata,
            connection_type=self.connection_type,
        )

    def get_combined_metadata(
        self, api_client: "InternalAPIClient", metadata: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Get combined workflow and usage metadata.

        Returns:
            dict[str, Any]: Combined metadata including workflow and usage data.
        """
        file_execution_id = self.file_execution_id
        usage_metadata = api_client.get_aggregated_token_count(file_execution_id)

        if metadata and usage_metadata:
            metadata["usage"] = usage_metadata.to_dict()
        return metadata

    def insert_into_db(
        self,
        input_file_path: str,
        tool_execution_result: str = None,
        metadata: dict[str, Any] = None,
        file_execution_id: str = None,
        error_message: str = None,
        api_client: "InternalAPIClient" = None,
    ) -> None:
        """Insert data into the database (following production pattern)."""
        # If no data and no error, don't execute CREATE or INSERT query
        if not (tool_execution_result or error_message):
            raise ValueError("No tool_execution_result or error_message provided")

        if error_message:
            logger.info(
                f"Proceeding with error record insertion for {input_file_path}: {error_message}"
            )

        # Store file_execution_id for logging
        if file_execution_id:
            self.current_file_execution_id = file_execution_id

        # Extract connector instance details from instance variables (now properly set)
        connector_id = self.connector_id
        connector_settings = self.connector_settings

        logger.info(f"Database destination - Connector ID: {connector_id}")
        logger.info(
            f"Database destination - Connector settings available: {bool(connector_settings)}"
        )
        logger.info(
            f"Database destination - Settings keys: {list(self.settings.keys()) if self.settings else 'None'}"
        )

        if not connector_id:
            raise ValueError("No connector_id provided in destination configuration")

        if not connector_settings:
            raise ValueError(
                "No connector_settings provided in destination configuration"
            )

        db_class = WorkerDatabaseUtils.get_db_class(
            connector_id=connector_id,
            connector_settings=connector_settings,
        )

        # Get combined metadata including usage data
        metadata = self.get_combined_metadata(api_client, metadata)
        logger.info(f"Database destination - Metadata: {metadata}")

        # Get table configuration from destination settings (table-specific config)
        table_name = str(self.settings.get("table", "unstract_results"))
        include_agent = bool(self.settings.get("includeAgent", False))
        include_timestamp = bool(self.settings.get("includeTimestamp", False))
        agent_name = str(self.settings.get("agentName", "UNSTRACT_DBWRITER"))
        column_mode = str(
            self.settings.get("columnMode", "WRITE_JSON_TO_A_SINGLE_COLUMN")
        )
        single_column_name = str(self.settings.get("singleColumnName", "data"))
        file_path_name = str(self.settings.get("filePath", "file_path"))
        execution_id_name = str(self.settings.get("executionId", "execution_id"))

        # Get tool execution result (use provided result only)
        data = tool_execution_result

        # Remove metadata from result
        # Tool text-extractor returns data in the form of string.
        # Don't pop out metadata in this case.
        if isinstance(data, dict):
            data.pop("metadata", None)

        # Use the workflow execution ID - warn if not available
        if not self.execution_id:
            logger.warning("Workflow execution_id not provided, using NULL in database")
            execution_id = None
        else:
            execution_id = self.execution_id

        engine = None
        try:
            logger.info(f"Creating database connection with connector ID: {connector_id}")
            db_class = WorkerDatabaseUtils.get_db_class(
                connector_id=connector_id,
                connector_settings=connector_settings,
            )
            table_info = db_class.get_information_schema(table_name=table_name)

            logger.info(
                f"destination connector table_name: {table_name} with table_info: {table_info}"
            )
            engine = db_class.get_engine()

            if table_info:
                if db_class.has_no_metadata(table_info=table_info):
                    table_info = WorkerDatabaseUtils.migrate_table_to_v2(
                        db_class=db_class,
                        engine=engine,
                        table_name=table_name,
                        column_name=single_column_name,
                    )

            logger.info(f"Creating table {table_name} if not exists")

            values = WorkerDatabaseUtils.get_columns_and_values(
                column_mode_str=column_mode,
                data=data,
                include_timestamp=include_timestamp,
                include_agent=include_agent,
                agent_name=agent_name,
                single_column_name=single_column_name,
                file_path_name=file_path_name,
                execution_id_name=execution_id_name,
                file_path=input_file_path,
                execution_id=execution_id,
                metadata=metadata,
                error=error_message,
            )

            WorkerDatabaseUtils.create_table_if_not_exists(
                db_class=db_class,
                engine=engine,
                table_name=table_name,
                database_entry=values,
            )

            logger.info(f"Preparing SQL query data for table {table_name}")
            sql_columns_and_values = WorkerDatabaseUtils.get_sql_query_data(
                conn_cls=db_class,
                table_name=table_name,
                values=values,
            )
            logger.info(
                f"sql_columns_and_values for table_name: {table_name} are: {sql_columns_and_values}"
            )
            logger.info(
                f"Executing insert query for {len(sql_columns_and_values)} columns"
            )
            WorkerDatabaseUtils.execute_write_query(
                db_class=db_class,
                engine=engine,
                table_name=table_name,
                sql_keys=list(sql_columns_and_values.keys()),
                sql_values=list(sql_columns_and_values.values()),
            )

            logger.info(f"Successfully inserted data into database table {table_name}")

            # Log to UI with file_execution_id for better correlation
            if self.workflow_log and hasattr(self, "current_file_execution_id"):
                log_file_info(
                    self.workflow_log,
                    self.current_file_execution_id,
                    f"📥 Data successfully inserted into database table '{table_name}'",
                )
        except ConnectorError as e:
            error_msg = f"Database connection failed for {input_file_path}: {str(e)}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = (
                f"Failed to insert data into database for {input_file_path}: {str(e)}"
            )
            logger.error(error_msg)
            raise
        finally:
            self._close_engine(engine, input_file_path)

    def _close_engine(self, engine: Any, input_file_path: str) -> None:
        """Safely close database engine."""
        if engine:
            try:
                engine.close()
            except Exception as e:
                logger.error(
                    f"Failed to close database engine for {input_file_path}: {str(e)}"
                )

    def copy_output_to_output_directory(
        self,
        input_file_path: str,
        file_execution_id: str = None,
        api_client: Optional["InternalAPIClient"] = None,
    ) -> None:
        """Copy output to the destination directory (following backend production pattern).

        This method should ONLY be called for TASK workflows where destination is FILESYSTEM.
        ETL workflows (destination=DATABASE) use insert_into_db() instead.
        API workflows don't use this destination copying logic.
        """
        # Store file_execution_id for logging
        if file_execution_id:
            self.current_file_execution_id = file_execution_id

        # ARCHITECTURE VALIDATION: Ensure this is only called for TASK workflows
        if api_client and self.workflow_id:
            if self.connection_type != CoreConnectionType.FILESYSTEM.value:
                logger.warning(
                    f"copy_output_to_output_directory called for destination connection_type {self.connection_type} with workflow {self.workflow_id} - this should only be used for {CoreConnectionType.FILESYSTEM.value} workflows"
                )
                return

        # Copy output to filesystem destination

        try:
            # Get destination connector settings - exactly like backend
            if not self.connector_id or not self.connector_settings:
                raise ValueError(
                    f"Missing destination connector configuration: connector_id={self.connector_id}, "
                    f"settings={bool(self.connector_settings)}"
                )

            # Import necessary modules for file operations

            # Get connector settings and configuration like backend (lines 262-265)
            connector_settings = self.connector_settings
            destination_configurations = self.settings or {}

            # Extract destination path configuration using enums to prevent camelCase/snake_case issues
            root_path = str(connector_settings.get(DestinationConfigKey.PATH, ""))
            output_directory = str(
                destination_configurations.get(DestinationConfigKey.OUTPUT_FOLDER, "/")
            )

            # Get the destination connector instance (lines 270-272)
            logger.debug(f"Initializing destination connector: {self.connector_id}")
            connector_service = WorkerConnectorService(api_client)
            destination_fs = connector_service._get_destination_connector(
                connector_id=self.connector_id, connector_settings=connector_settings
            )

            # Get connector root directory like backend (lines 273-275)
            output_directory = destination_fs.get_connector_root_dir(
                input_dir=output_directory, root_path=root_path
            )

            # Build destination volume path like backend (lines 277-279)
            # Backend uses self.file_execution_dir which maps to our execution path
            execution_dir_path = f"unstract/execution/{self.organization_id}/{self.workflow_id}/{self.execution_id}/{file_execution_id}"
            destination_volume_path = os.path.join(
                execution_dir_path, ToolExecKey.OUTPUT_DIR
            )

            # Get workflow execution file system for reading (like backend lines 285-286)
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            fs = file_system.get_file_storage()

            # Backend logic: Create destination directory if needed (line 282)
            try:
                # CONNECTOR COMPATIBILITY: Skip root directory creation for certain paths
                normalized_output_dir = output_directory.strip("/")
                if normalized_output_dir and normalized_output_dir != ".":
                    destination_fs.create_dir_if_not_exists(
                        input_dir=normalized_output_dir
                    )
                else:
                    logger.debug(
                        f"Skipping root directory creation for path: '{output_directory}'"
                    )
            except Exception as e:
                logger.warning(
                    f"Could not create destination directory {output_directory}: {e}"
                )

            # Backend logic: Walk the OUTPUT_DIR and copy everything (lines 287-307)
            copied_files = []
            failed_files = []
            total_copied = 0

            # Check if OUTPUT_DIR exists before walking
            if not fs.exists(destination_volume_path):
                logger.warning(
                    f"Output directory does not exist: {destination_volume_path}"
                )
                logger.info(
                    "No output files to copy - workflow may not have produced output"
                )
            else:
                # Walk directory structure like backend (lines 289-307)
                try:
                    dir_path = fs.walk(str(destination_volume_path))

                    for root, dirs, files in dir_path:
                        # Create directories in destination (lines 290-296)
                        for dir_name in dirs:
                            current_dir = os.path.join(
                                output_directory,
                                os.path.relpath(root, destination_volume_path),
                                dir_name,
                            )
                            try:
                                # CONNECTOR COMPATIBILITY: Skip root directory creation for certain paths
                                normalized_current_dir = current_dir.strip("/")
                                if (
                                    normalized_current_dir
                                    and normalized_current_dir != "."
                                ):
                                    destination_fs.create_dir_if_not_exists(
                                        input_dir=normalized_current_dir
                                    )
                                    logger.debug(
                                        f"Created directory: {normalized_current_dir}"
                                    )
                                else:
                                    logger.debug(
                                        f"Skipping root directory creation for path: '{current_dir}'"
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"Could not create directory {current_dir}: {e}"
                                )

                        # Copy files (lines 298-307)
                        for file_name in files:
                            source_path = os.path.join(root, file_name)

                            # Calculate relative path and handle path construction properly
                            relative_path = os.path.relpath(root, destination_volume_path)

                            if relative_path == "." or not relative_path:
                                # When root == destination_volume_path, use output_directory directly
                                destination_path = os.path.join(
                                    output_directory, file_name
                                )
                            else:
                                destination_path = os.path.join(
                                    output_directory,
                                    relative_path,
                                    file_name,
                                )

                            # Normalize path and validate
                            destination_path = os.path.normpath(destination_path)

                            # ARCHITECTURE FIX: Proper error handling instead of inconsistent fallbacks
                            if not destination_path or destination_path in [".", "/"]:
                                error_msg = f"Invalid destination path '{destination_path}' constructed for file {file_name}"
                                logger.error(f"ERROR: {error_msg}")
                                logger.error(
                                    f"ERROR: Debug info - output_directory='{output_directory}', relative_path='{relative_path}', root='{root}', destination_volume_path='{destination_volume_path}'"
                                )
                                raise ValueError(error_msg)

                            try:
                                # CONNECTOR COMPATIBILITY: Handle path normalization for worker context
                                # Remove leading slash that can cause issues with various connectors
                                final_destination_path = (
                                    destination_path.lstrip("/")
                                    if destination_path.startswith("/")
                                    else destination_path
                                )

                                # Validate the final path is not empty after normalization
                                if (
                                    not final_destination_path
                                    or final_destination_path in [".", ""]
                                ):
                                    raise ValueError(
                                        f"Invalid destination path after normalization: '{final_destination_path}' (original: '{destination_path}')"
                                    )

                                destination_fs.upload_file_to_storage(
                                    source_path=source_path,
                                    destination_path=final_destination_path,
                                )
                                copied_files.append(file_name)
                                total_copied += 1
                                logger.debug(f"✅ Successfully copied: {file_name}")

                            except Exception as copy_error:
                                logger.error(
                                    f"Failed to copy {file_name}: {copy_error}",
                                    exc_info=True,
                                )
                                failed_files.append(file_name)
                                # Continue with other files even if one fails

                except Exception as walk_error:
                    logger.error(
                        f"Failed to walk output directory {destination_volume_path}: {walk_error}"
                    )

            # Report results - handle both successes and failures
            if failed_files:
                # If any files failed, this should be treated as an error
                failed_count = len(failed_files)
                if failed_count == 1:
                    error_message = (
                        f"❌ Failed to copy file to destination: {failed_files[0]}"
                    )
                else:
                    error_message = (
                        f"❌ Failed to copy {failed_count} files to destination"
                    )
                logger.error(error_message)

                # Log to UI with file_execution_id
                if self.workflow_log and hasattr(self, "current_file_execution_id"):
                    log_file_info(
                        self.workflow_log,
                        self.current_file_execution_id,
                        error_message,
                    )

                # Raise exception to trigger proper error handling
                raise Exception(f"Destination copy failed: {error_message}")
            elif total_copied > 0:
                success_message = f"💾 Successfully copied {total_copied} files to filesystem destination"
                logger.info(success_message)

                # Log to UI
                if self.workflow_log and hasattr(self, "current_file_execution_id"):
                    log_file_info(
                        self.workflow_log,
                        self.current_file_execution_id,
                        success_message,
                    )
            else:
                success_message = (
                    "💾 No output files found to copy to filesystem destination"
                )
                logger.info(success_message)

                # Log to UI
                if self.workflow_log and hasattr(self, "current_file_execution_id"):
                    log_file_info(
                        self.workflow_log,
                        self.current_file_execution_id,
                        success_message,
                    )

        except Exception as e:
            error_msg = f"Failed to copy files to filesystem destination: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # Log error to UI
            if self.workflow_log and hasattr(self, "current_file_execution_id"):
                log_file_info(
                    self.workflow_log,
                    self.current_file_execution_id,
                    f"❌ {error_msg}",
                )

            # Re-raise the exception so that destination processing can fail properly
            raise Exception(f"Destination filesystem copy failed: {str(e)}") from e

    def get_tool_execution_result(
        self, file_history=None, tool_execution_result: str = None
    ) -> Any:
        """Get result data from the output file (following production pattern)."""
        if tool_execution_result:
            return tool_execution_result

        if file_history and hasattr(file_history, "result") and file_history.result:
            return self.parse_string(file_history.result)

        # Default fallback - could be enhanced to read from actual execution files
        return None

    def get_tool_execution_result_from_execution_context(
        self,
        workflow_id: str,
        execution_id: str,
        file_execution_id: str,
        organization_id: str,
    ) -> dict | str:
        """Get tool execution result using proper execution context (preferred method)."""
        try:
            # Use ExecutionFileHandler to get proper paths (matching backend)
            file_handler = ExecutionFileHandler(
                workflow_id=workflow_id,
                execution_id=execution_id,
                organization_id=organization_id,
                file_execution_id=file_execution_id,
            )
            metadata_file_path = file_handler.metadata_file
            # Get workflow metadata (following backend pattern)
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()

            if not metadata_file_path:
                return None

            if not file_storage.exists(metadata_file_path):
                return None

            metadata_content = file_storage.read(path=metadata_file_path, mode="r")
            metadata = json.loads(metadata_content)

            # Get output type from metadata (following backend pattern)
            output_type = self._get_output_type_from_metadata(metadata)

            # Get the output file path using the file handler (matching backend pattern)
            output_file_path = file_handler.infile

            if not output_file_path:
                return None

            if not file_storage.exists(output_file_path):
                return None

            file_type = file_storage.mime_type(path=output_file_path)
            if output_type == ToolOutputType.JSON:
                if file_type != EXT_MIME_MAP[ToolOutputType.JSON.lower()]:
                    msg = f"Expected tool output type: JSON, got: '{file_type}'"
                    logger.error(msg)
                    raise Exception(msg)
                file_content = file_storage.read(output_file_path, mode="r")
                result = json.loads(file_content)
                return result
            elif output_type == ToolOutputType.TXT:
                if file_type != EXT_MIME_MAP[ToolOutputType.TXT.lower()]:
                    msg = f"Expected tool output type: TXT, got: '{file_type}'"
                    logger.error(msg)
                    raise Exception(msg)
                file_content = file_storage.read(output_file_path, mode="r")
                result = file_content.encode("utf-8").decode("unicode-escape")
                return result
            else:
                raise Exception(f"Unsupported output type: {output_type}")

        except Exception as e:
            logger.error(
                f"Exception while getting tool execution result from execution context: {str(e)}",
                exc_info=True,
            )
            raise

    def _get_output_type_from_metadata(self, metadata: dict[str, Any]) -> str:
        """Get output type from metadata (following backend pattern)."""
        try:
            # Get tool metadata list
            tool_metadata = metadata.get(MetaDataKey.TOOL_METADATA, [])
            if not tool_metadata:
                logger.warning("No tool metadata found, defaulting to TXT output")
                return ToolOutputType.TXT

            # Get last tool metadata (like backend)
            last_tool_metadata = tool_metadata[-1]
            output_type = last_tool_metadata.get(
                ToolMetadataKey.OUTPUT_TYPE, ToolOutputType.TXT
            )

            logger.debug(f"Detected output type: {output_type}")
            return output_type

        except Exception as e:
            logger.error(f"Failed to get output type from metadata: {str(e)}")
            return ToolOutputType.TXT

    def parse_string(self, original_string: str) -> Any:
        """Parse the given string, attempting to evaluate it as a Python literal."""
        try:
            # Try to evaluate as a Python literal
            python_literal = ast.literal_eval(original_string)
            return python_literal
        except (SyntaxError, ValueError):
            # If evaluating as a Python literal fails,
            # assume it's a plain string
            return original_string

    def get_metadata(self, file_history=None) -> dict[str, Any] | None:
        """Get metadata from the output file (matching backend pattern).

        This matches backend DestinationConnector.get_metadata.
        """
        if file_history:
            if self.has_valid_metadata(getattr(file_history, "metadata", None)):
                return self.parse_string(file_history.metadata)
            else:
                return None
        metadata: dict[str, Any] = self._get_workflow_metadata()
        return metadata

    def _get_workflow_metadata(self) -> dict[str, Any]:
        """Get metadata from the workflow (matching backend pattern)."""
        file_handler = ExecutionFileHandler(
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            organization_id=self.organization_id,
            file_execution_id=self.file_execution_id,
        )
        metadata: dict[str, Any] = file_handler.get_workflow_metadata()
        return metadata

    def has_valid_metadata(self, metadata: Any) -> bool:
        """Check if metadata is valid (matching backend pattern)."""
        # Check if metadata is not None and metadata is a non-empty string
        if not metadata:
            return False
        if not isinstance(metadata, str):
            return False
        if metadata.strip().lower() == "none":
            return False
        return True

    def _should_handle_hitl(
        self,
        file_name: str,
        file_hash: FileHashData,
        workflow: dict[str, Any],
        api_client: Optional["InternalAPIClient"] = None,
        tool_execution_result: dict | str | None = None,
        error: str | None = None,
    ) -> bool:
        """Determines if HITL processing should be performed, returning True if data was pushed to the queue.

        This method replicates the backend DestinationConnector._should_handle_hitl logic.
        """
        logger.info(f"{file_name}: checking if file is eligible for HITL")
        if error:
            logger.error(
                f"{file_name}: file is not eligible for HITL due to error: {error}"
            )
            return False

        # Check if API deployment requested HITL override
        if self.hitl_queue_name:
            logger.info(f"{file_name}: Pushing to HITL queue")
            return True

        # Skip HITL validation if we're using file_history and no execution result is available
        if self.is_api:
            logger.info(
                f"{file_name}: Skipping HITL validation as it's an API deployment"
            )
            return False
        if not self.use_file_history:
            logger.info(
                f"{file_name}: Skipping HITL validation as we're not using file_history"
            )
            return False
        if not file_hash.is_manualreview_required:
            logger.info(f"{file_name}: File is not marked for manual review")
            return False

        # Use class-level manual review service
        manual_review_service = self._ensure_manual_review_service(api_client)
        if not manual_review_service:
            logger.info(f"No manual review service available for {file_name}")
            return False

        workflow_util = manual_review_service.get_workflow_util()
        is_to_hitl = workflow_util.validate_db_rule(
            tool_execution_result,
            workflow,
            file_hash.file_destination,
            file_hash.is_manualreview_required,
        )
        logger.info(f"File {file_name} checked for manual review: {is_to_hitl}")
        if is_to_hitl:
            return True
        return False

    def _push_data_to_queue(
        self,
        file_name: str,
        workflow: dict[str, Any],
        input_file_path: str,
        file_execution_id: str,
        tool_execution_result: str = None,
        api_client: Optional["InternalAPIClient"] = None,
    ) -> None:
        """Handle manual review queue processing (following production pattern).

        This method replicates the backend DestinationConnector._push_to_queue logic.
        """
        if not has_manual_review_plugin():
            logger.warning(f"No manual review service available to enqueue {file_name}")
            return
        logger.info(f"Pushing {file_name} to manual review queue")
        log_file_info(
            self.workflow_log,
            file_execution_id,
            f"🔄 File '{file_name}' sending to manual review queue",
        )

        try:
            # Ensure manual review service is available and use it
            manual_review_service = self._ensure_manual_review_service(api_client)

            # Get tool execution result if not provided
            if not tool_execution_result:
                tool_execution_result = (
                    self.get_tool_execution_result_from_execution_context(
                        workflow_id=self.workflow_id,
                        execution_id=self.execution_id,
                        file_execution_id=file_execution_id,
                        organization_id=self.organization_id,
                    )
                )

            if not tool_execution_result:
                logger.warning(
                    f"No tool execution result available for {file_name}, skipping queue"
                )
                return

            # Get queue name using backend pattern
            queue_name = self._get_review_queue_name()
            # Use workflow util via plugin architecture (handles OSS/Enterprise automatically)
            workflow_util = manual_review_service.get_workflow_util()

            # Read file content based on deployment type (matching backend logic)
            if self.is_api:
                # For API deployments, read from workflow execution storage (no fallback in backend)
                file_content_base64 = self._read_file_content_for_queue(
                    input_file_path, file_name
                )
                ttl_seconds = None
            else:
                # For ETL/TASK workflows, read from source connector (like backend)
                file_content_base64 = self._read_file_from_source_connector(
                    input_file_path, file_name, workflow
                )
                ttl_seconds = workflow_util.get_hitl_ttl_seconds(str(self.workflow_id))

            # Get metadata (whisper-hash, etc.)
            metadata = self.get_metadata()
            whisper_hash = metadata.get("whisper-hash") if metadata else None
            extracted_text = metadata.get("extracted_text") if metadata else None

            # Create queue result matching backend QueueResult structure
            queue_result = QueueResult(
                file=file_name,
                status=QueueResultStatus.SUCCESS,
                result=tool_execution_result,
                workflow_id=str(self.workflow_id),
                whisper_hash=whisper_hash,
                file_execution_id=file_execution_id,
                extracted_text=extracted_text,
                ttl_seconds=ttl_seconds,
            )

            # Only include file_content if provided (backend API will handle it)
            if file_content_base64 is not None:
                queue_result.file_content = file_content_base64

            workflow_util.enqueue_manual_review(
                queue_name=queue_name,
                message=queue_result.to_dict(),
                organization_id=self.organization_id,
            )

            # Log successful enqueue (common for both paths)
            log_file_info(
                self.workflow_log,
                file_execution_id,
                f"✅ File '{file_name}' sent to manual review queue '{queue_name}'",
            )

            logger.info(
                f"✅ MANUAL REVIEW: File '{file_name}' sent to manual review queue '{queue_name}' successfully"
            )

        except Exception as e:
            logger.error(f"Failed to push {file_name} to manual review queue: {e}")
            raise

    def _get_review_queue_name(self) -> str:
        """Generate review queue name with optional HITL override for manual review processing.

        This method replicates the backend DestinationConnector._get_review_queue_name logic.
        """
        logger.debug(f"Queue naming - hitl_queue_name={self.hitl_queue_name}")

        # Base queue format: review_queue_{org}_{workflow_id}
        base_queue_name = f"review_queue_{self.organization_id}_{str(self.workflow_id)}"

        if self.hitl_queue_name:
            # Custom HITL queue with user-specified name
            q_name = f"{base_queue_name}:{self.hitl_queue_name}"
            logger.debug(f"Using custom HITL queue: {q_name}")
        else:
            # Standard queue format for workflow-based processing
            q_name = base_queue_name
            logger.debug(f"Using standard queue name: {q_name}")

        return q_name

    def _read_file_content_for_queue(self, input_file_path: str, file_name: str) -> str:
        """Read and encode file content for queue message from execution storage.

        This method replicates the backend DestinationConnector._read_file_content_for_queue logic.
        """
        try:
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()

            if not file_storage.exists(input_file_path):
                raise FileNotFoundError(f"File not found: {input_file_path}")

            file_bytes = file_storage.read(input_file_path, mode="rb")
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")
            return base64.b64encode(file_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to read file content for {file_name}: {e}")
            raise OSError(f"Failed to read file content for queue: {e}")

    def _read_file_from_source_connector(
        self, input_file_path: str, file_name: str, workflow: dict[str, Any]
    ) -> str:
        """Read and encode file content from source connector for ETL/TASK workflows.

        This method replicates the backend logic: source_fs.open(input_file_path, "rb")
        """
        try:
            # Use source connector configuration (not destination connector!)
            if not self.source_connector_id or not self.source_connector_settings:
                # Try to get source connector info from workflow data as fallback
                source_connector_id = (
                    workflow.get("source_connector_id") if workflow else None
                )
                source_connector_settings = (
                    workflow.get("source_connector_settings") if workflow else None
                )

                if not source_connector_id or not source_connector_settings:
                    raise ValueError(
                        f"Source connector configuration not available for {file_name}"
                    )
            else:
                source_connector_id = self.source_connector_id
                source_connector_settings = self.source_connector_settings

            logger.debug(
                f"Using source connector {source_connector_id} to read {file_name}"
            )

            # Import connector operations

            # Get the source connector instance (not destination!)
            connectorkit = Connectorkit()
            connector_class = connectorkit.get_connector_class_by_connector_id(
                source_connector_id
            )
            connector_instance = connector_class(source_connector_settings)

            # Get fsspec filesystem (like backend: self.get_fsspec())
            source_fs = connector_instance.get_fsspec_fs()

            # Read file content (like backend: source_fs.open(input_file_path, "rb"))
            with source_fs.open(input_file_path, "rb") as remote_file:
                file_content = remote_file.read()
                file_content_base64 = base64.b64encode(file_content).decode("utf-8")

            logger.info(
                f"Successfully read {len(file_content)} bytes from source connector for {file_name}"
            )
            return file_content_base64

        except Exception as e:
            logger.error(
                f"Failed to read file from source connector for {file_name}: {e}"
            )
            raise OSError(f"Failed to read file from source connector: {e}")


# Alias for backward compatibility
DestinationConnector = WorkerDestinationConnector
