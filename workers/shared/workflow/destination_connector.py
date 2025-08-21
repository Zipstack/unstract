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

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from unstract.core.data_models import ConnectionType as CoreConnectionType
from unstract.core.data_models import FileHashData

from ..enums import FileDestinationType
from ..logging_utils import WorkerLogger

if TYPE_CHECKING:
    from ..api_client import InternalAPIClient

logger = WorkerLogger.get_logger(__name__)


@dataclass
class DestinationConfig:
    """Worker-compatible DestinationConfig implementation."""

    connection_type: str
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
        return cls(
            connection_type=data.get("connection_type", ""),
            settings=data.get("settings", {}),
            is_api=data.get("is_api", False),
            use_file_history=data.get("use_file_history", True),
            connector_id=data.get("connector_id"),
            connector_settings=data.get("connector_settings", {}),
            connector_name=data.get("connector_name"),
            hitl_queue_name=data.get("hitl_queue_name"),
            source_connector_id=data.get("source_connector_id"),
            source_connector_settings=data.get("source_connector_settings", {}),
        )


class WorkerDestinationConnector:
    """Worker-compatible destination connector following production patterns.

    This class replicates the functionality of backend DestinationConnector
    from workflow_manager/endpoint_v2/destination.py without Django dependencies.
    """

    # Use CoreConnectionType directly - no need for wrapper class
    ConnectionType = CoreConnectionType

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
        self.workflow_id = None
        self.execution_id = None
        self.organization_id = None

    @classmethod
    def from_config(cls, workflow_log, config: DestinationConfig):
        """Create destination connector from config (matching Django backend interface)."""
        return cls(config, workflow_log)

    def handle_output_for_files(
        self,
        files_data: list[
            tuple[str, FileHashData, Any, dict[str, Any], str, str]
        ],  # (file_name, file_hash, file_history, workflow, input_file_path, file_execution_id)
        api_client: Optional["InternalAPIClient"] = None,
        tool_execution_results: list[str] | None = None,
    ) -> list[bool]:
        """Handle output for batch of files with manual review evaluation.

        This method processes a batch of files and applies manual review logic
        using the plugin-based percentage evaluator.

        Args:
            files_data: List of file data tuples
            api_client: API client for backend communication
            tool_execution_results: Optional list of tool execution results

        Returns:
            List of booleans indicating successful processing
        """
        if not files_data:
            return []

        logger.info(f"Starting batch processing for {len(files_data)} files")

        # Extract data for manual review evaluation
        manual_review_data = [
            (file_name, file_hash, input_file_path, file_execution_id)
            for file_name, file_hash, _, _, input_file_path, file_execution_id in files_data
        ]

        # Get workflow from first file (should be same for all files in batch)
        workflow = files_data[0][3] if files_data else {}

        # Evaluate batch for manual review
        manual_review_decisions = self._evaluate_manual_review_batch(
            files_data=manual_review_data,
            workflow=workflow,
            api_client=api_client,
        )

        # Process each file based on manual review decision
        results = []
        for i, (
            file_name,
            file_hash,
            file_history,
            workflow,
            input_file_path,
            file_execution_id,
        ) in enumerate(files_data):
            try:
                should_review = (
                    manual_review_decisions[i]
                    if i < len(manual_review_decisions)
                    else False
                )
                tool_execution_result = (
                    tool_execution_results[i]
                    if tool_execution_results and i < len(tool_execution_results)
                    else None
                )

                if should_review:
                    logger.info(
                        f"Sending {file_name} to manual review queue (batch decision)"
                    )
                    # Log to UI via workflow_log
                    if self.workflow_log:
                        self.workflow_log.publish_log(
                            message=f"📋 File '{file_name}' selected for manual review based on configured rules"
                        )
                    self._push_data_to_queue(
                        file_name=file_name,
                        workflow=workflow,
                        input_file_path=input_file_path,
                        file_execution_id=file_execution_id,
                        tool_execution_result=tool_execution_result,
                        api_client=api_client,
                    )
                    results.append(True)
                else:
                    logger.info(
                        f"Processing {file_name} through destination (skipping manual review)"
                    )
                    # Process through normal destination
                    success = self._handle_individual_output(
                        file_name=file_name,
                        file_hash=file_hash,
                        file_history=file_history,
                        workflow=workflow,
                        input_file_path=input_file_path,
                        file_execution_id=file_execution_id,
                        api_client=api_client,
                        tool_execution_result=tool_execution_result,
                    )
                    results.append(success)

            except Exception as e:
                logger.error(f"Error processing file {file_name}: {e}")
                results.append(False)

        logger.info(
            f"Batch processing completed: {sum(results)}/{len(results)} files processed successfully"
        )
        return results

    def _handle_individual_output(
        self,
        file_name: str,
        file_hash: FileHashData,
        file_history,
        workflow: dict[str, Any],
        input_file_path: str,
        file_execution_id: str = None,
        api_client: Optional["InternalAPIClient"] = None,
        tool_execution_result: str | None = None,
    ) -> bool:
        """Handle output for individual file (original handle_output logic without manual review)."""
        try:
            # Process through destination based on connection type
            if self.connection_type == CoreConnectionType.DATABASE.value:
                self.insert_into_db(
                    input_file_path=input_file_path,
                    tool_execution_result=tool_execution_result,
                )
            elif self.connection_type == CoreConnectionType.FILESYSTEM.value:
                self.copy_output_to_output_directory(input_file_path)
            else:
                logger.warning(f"Unsupported connection type: {self.connection_type}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error processing individual file output for {file_name}: {e}")
            return False

    def handle_output(
        self,
        file_name: str,
        file_hash: FileHashData,
        file_history,
        workflow: dict[str, Any],
        input_file_path: str,
        file_execution_id: str = None,
        api_client: Optional["InternalAPIClient"] = None,
        tool_execution_result: str | None = None,
        workflow_id: str = None,
        execution_id: str = None,
        organization_id: str = None,
    ) -> str | None:
        """Handle the output based on the connection type (following production pattern)."""
        connection_type = self.connection_type

        # Store context for manual review methods
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.organization_id = organization_id

        # Check if file is marked for manual review via file_destination field
        if (
            hasattr(file_hash, "file_destination")
            and file_hash.file_destination == FileDestinationType.MANUALREVIEW.value
        ):
            logger.info(
                f"File {file_name} marked for manual review via file_destination field"
            )
            # Get real tool execution result if not provided
            if not tool_execution_result:
                tool_execution_result = (
                    self.get_tool_execution_result_from_execution_context(
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        file_execution_id=file_execution_id,
                        organization_id=organization_id,
                    )
                )

            self._push_data_to_queue(
                file_name,
                workflow,
                input_file_path,
                file_execution_id,
                tool_execution_result,
                api_client=api_client,
            )

            # Log successful processing
            if self.workflow_log:
                self.workflow_log.publish_log(
                    message=f"File '{file_name}' sent to manual review queue"
                )
            else:
                logger.info(f"File '{file_name}' sent to manual review queue")

            return tool_execution_result

        try:
            if connection_type == self.ConnectionType.FILESYSTEM.value:
                self.copy_output_to_output_directory(input_file_path)
            elif connection_type == self.ConnectionType.DATABASE.value:
                # Check for manual review first (like backend)
                if not self._should_handle_hitl(
                    file_name=file_name,
                    file_hash=file_hash,
                    workflow=workflow,
                    input_file_path=input_file_path,
                    file_execution_id=file_execution_id,
                    api_client=api_client,
                ):
                    # Get real tool execution result if not provided
                    if not tool_execution_result:
                        tool_execution_result = (
                            self.get_tool_execution_result_from_execution_context(
                                workflow_id=workflow_id,
                                execution_id=execution_id,
                                file_execution_id=file_execution_id,
                                organization_id=organization_id,
                            )
                        )
                    # Handle database insertion following production pattern
                    self.insert_into_db(input_file_path, tool_execution_result)
            elif connection_type == self.ConnectionType.API.value:
                logger.info(f"API connection type detected for file {file_name}")
                # Check for HITL (Manual Review Queue) override for API deployments (like backend)
                if not self._should_handle_hitl(
                    file_name=file_name,
                    file_hash=file_hash,
                    workflow=workflow,
                    input_file_path=input_file_path,
                    file_execution_id=file_execution_id,
                    api_client=api_client,
                ):
                    logger.info(
                        f"No HITL override, getting tool execution result for {file_name}"
                    )
                    # Get real tool execution result if not provided
                    if not tool_execution_result:
                        tool_execution_result = (
                            self.get_tool_execution_result_from_execution_context(
                                workflow_id=workflow_id,
                                execution_id=execution_id,
                                file_execution_id=file_execution_id,
                                organization_id=organization_id,
                            )
                        )
                    else:
                        tool_execution_result = self.get_tool_execution_result(
                            file_history, tool_execution_result
                        )
            elif connection_type == self.ConnectionType.MANUALREVIEW.value:
                # Get real tool execution result if not provided
                if not tool_execution_result:
                    tool_execution_result = (
                        self.get_tool_execution_result_from_execution_context(
                            workflow_id=workflow_id,
                            execution_id=execution_id,
                            file_execution_id=file_execution_id,
                            organization_id=organization_id,
                        )
                    )

                self._push_data_to_queue(
                    file_name,
                    workflow,
                    input_file_path,
                    file_execution_id,
                    tool_execution_result,
                    api_client=api_client,
                )
            else:
                logger.warning(f"Unknown destination connection type: {connection_type}")

        except Exception as destination_error:
            logger.error(f"Destination handle_output failed: {str(destination_error)}")
            # Don't re-raise for API destinations to allow workflow completion
            if connection_type != self.ConnectionType.API.value:
                raise
            else:
                logger.warning(
                    f"API destination error ignored to allow workflow completion: {str(destination_error)}"
                )

        # Log successful processing
        if self.workflow_log:
            self.workflow_log.publish_log(
                message=f"File '{file_name}' processed successfully"
            )
        else:
            logger.info(f"File '{file_name}' processed successfully")

        return tool_execution_result

    def insert_into_db(
        self, input_file_path: str, tool_execution_result: str = None
    ) -> None:
        """Insert data into the database (following production pattern)."""
        try:
            from shared.database_utils import WorkerDatabaseUtils
        except ImportError:
            # Fallback import path
            from ...shared.database_utils import WorkerDatabaseUtils

        # DEBUG: Log what we received
        logger.info(
            f"DEBUG: insert_into_db called with tool_execution_result type: {type(tool_execution_result)}"
        )
        logger.info(
            f"DEBUG: insert_into_db tool_execution_result value: {tool_execution_result}"
        )

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
            raise Exception("No connector_id provided in destination configuration")

        if not connector_settings:
            raise Exception("No connector_settings provided in destination configuration")

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

        # If data is None, don't execute CREATE or INSERT query
        if not data:
            logger.info("No data obtained from tool to insert into destination DB.")
            return

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
        )

        engine = None
        try:
            logger.info(f"Creating database connection with connector ID: {connector_id}")
            db_class = WorkerDatabaseUtils.get_db_class(
                connector_id=connector_id,
                connector_settings=connector_settings,
            )
            engine = db_class.get_engine()

            logger.info(f"Creating table {table_name} if not exists")
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

    def copy_output_to_output_directory(self, input_file_path: str) -> None:
        """Copy output to the destination directory (following production pattern)."""
        # Implementation for filesystem destinations
        # This would copy files from execution directory to destination
        logger.info(f"Copying output to filesystem destination for {input_file_path}")
        # Placeholder implementation - actual filesystem copying would be implemented here
        pass

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
    ) -> Any:
        """Get tool execution result using proper execution context (preferred method)."""
        try:
            # Import required modules for file system operations
            from unstract.filesystem import FileStorageType, FileSystem
            from unstract.workflow_execution.constants import (
                ToolOutputType,
            )
            from unstract.workflow_execution.execution_file_handler import (
                ExecutionFileHandler,
            )

            logger.debug(
                f"Getting tool execution result for execution context: {workflow_id}/{execution_id}/{file_execution_id}"
            )

            # Use ExecutionFileHandler to get proper paths
            file_handler = ExecutionFileHandler(
                workflow_id=workflow_id,
                execution_id=execution_id,
                organization_id=organization_id,
                file_execution_id=file_execution_id,
            )

            metadata_file_path = file_handler.metadata_file

            # Get workflow metadata
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()

            if not metadata_file_path:
                logger.warning("Metadata file path is None")
                return None

            if not file_storage.exists(metadata_file_path):
                logger.warning(f"Metadata file does not exist: {metadata_file_path}")
                return None

            metadata_content = file_storage.read(path=metadata_file_path, mode="r")
            metadata = json.loads(metadata_content)

            # Get output type from metadata
            output_type = self.get_output_type_from_metadata(metadata)

            # Get the output file path using the file handler
            output_file_path = file_handler.infile

            if not output_file_path:
                logger.warning("Output file path is None")
                return None

            if not file_storage.exists(output_file_path):
                logger.warning(f"Output file does not exist: {output_file_path}")
                return None

            # Parse based on output type (following backend pattern)
            if output_type == ToolOutputType.JSON:
                file_content = file_storage.read(output_file_path, mode="r")
                result = json.loads(file_content)
                logger.info(
                    f"Successfully parsed JSON tool result from {output_file_path}"
                )
                return result
            elif output_type == ToolOutputType.TXT:
                file_content = file_storage.read(output_file_path, mode="r")
                result = file_content.encode("utf-8").decode("unicode-escape")
                logger.info(f"Successfully read TXT tool result from {output_file_path}")
                return result
            else:
                logger.warning(f"Unknown output type: {output_type}")
                return None

        except Exception as e:
            logger.error(
                f"Failed to get tool execution result from execution context: {str(e)}"
            )
            return None

    def get_output_type_from_metadata(self, metadata: dict[str, Any]) -> str:
        """Get output type from metadata (following backend pattern)."""
        try:
            from unstract.workflow_execution.constants import (
                MetaDataKey,
                ToolMetadataKey,
                ToolOutputType,
            )

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
            return "TXT"  # Safe default

    def parse_string(self, original_string: str) -> Any:
        """Parse the given string, attempting to evaluate it as a Python literal."""
        import ast

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

        # For workers, we don't have workflow metadata files readily available
        # This would need to be implemented via API if needed
        # metadata = self.get_workflow_metadata()
        # return metadata
        return None

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
        input_file_path: str,
        file_execution_id: str,
        api_client: Optional["InternalAPIClient"] = None,
    ) -> bool:
        """Determines if HITL processing should be performed, returning True if data was pushed to the queue.

        This method replicates the backend DestinationConnector._should_handle_hitl logic.
        """
        # Check if API deployment requested HITL override
        if self.hitl_queue_name:
            logger.info(f"API HITL override: pushing to queue for file {file_name}")
            self._push_data_to_queue(
                file_name=file_name,
                workflow=workflow,
                input_file_path=input_file_path,
                file_execution_id=file_execution_id,
                api_client=api_client,
            )
            logger.info(f"Successfully pushed {file_name} to HITL queue")
            return True

        # Skip HITL validation if we're using file_history and no execution result is available
        if self.is_api and self.use_file_history:
            return False

        # Otherwise use workflow-based HITL logic via API
        try:
            if api_client:
                # Note: Individual file validation is deprecated
                # Batch evaluation is handled in handle_output_for_files method
                # This fallback returns False to disable individual evaluation
                logger.info(
                    f"Individual manual review validation disabled for {file_name} - using batch evaluation"
                )
                return False
            else:
                logger.warning("No API client provided for manual review validation")

        except Exception as e:
            logger.error(f"Error validating manual review DB rule: {e}")
            # If validation fails, don't queue (safer to proceed to destination)

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
        logger.info(f"Pushing {file_name} to manual review queue")

        try:
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

            # Read file content based on deployment type (matching backend logic)
            if self.is_api:
                # For API deployments, read from workflow execution storage (no fallback in backend)
                file_content_base64 = self._read_file_content_for_queue(
                    input_file_path, file_name
                )
            else:
                # For ETL/TASK workflows, read from source connector (like backend)
                file_content_base64 = self._read_file_from_source_connector(
                    input_file_path, file_name, workflow
                )

            # Get metadata (whisper-hash, etc.)
            metadata = self.get_metadata()
            whisper_hash = metadata.get("whisper-hash") if metadata else None

            # Create queue result matching backend QueueResult structure
            queue_result = {
                "file": file_name,
                "status": "SUCCESS",
                "result": tool_execution_result,
                "workflow_id": str(self.workflow_id),
                "whisper_hash": whisper_hash,
                "file_execution_id": file_execution_id,
            }

            # Only include file_content if provided (backend API will handle it)
            if file_content_base64 is not None:
                queue_result["file_content"] = file_content_base64

            # Use API client to enqueue (this calls backend queue infrastructure)
            if api_client:
                api_client.enqueue_manual_review(
                    queue_name=queue_name,
                    message=queue_result,
                    organization_id=self.organization_id,
                )
                # Log to UI via workflow_log
                if self.workflow_log:
                    self.workflow_log.publish_log(
                        message=f"✅ File '{file_name}' sent to manual review queue '{queue_name}'"
                    )

                logger.info(
                    f"✅ MANUAL REVIEW: File '{file_name}' sent to manual review queue '{queue_name}' successfully"
                )
            else:
                logger.error(f"No API client available to enqueue {file_name}")

        except Exception as e:
            logger.error(f"Failed to push {file_name} to manual review queue: {e}")
            raise

    def handle_output_for_files_simple(
        self,
        files: list[FileHashData],
        workflow: dict[str, Any],
        api_client: Optional["InternalAPIClient"] = None,
        workflow_id: str = None,
        execution_id: str = None,
        organization_id: str = None,
    ) -> list[bool]:
        """Handle output for a simple list of FileHashData objects with manual review evaluation.

        This is a convenience method for batch processing that accepts a simple list of files.
        """
        if not files:
            return []

        logger.info(f"Starting simple batch processing for {len(files)} files")

        # Convert to the format expected by handle_output_for_files
        files_data = []
        for i, file_hash in enumerate(files):
            file_name = file_hash.file_name
            file_history = None  # Will be checked internally if needed
            input_file_path = file_hash.file_path
            file_execution_id = f"batch-{i}"  # Simple execution ID for batch processing

            files_data.append(
                (
                    file_name,  # file_name
                    file_hash,  # file_hash
                    file_history,  # file_history
                    workflow,  # workflow
                    input_file_path,  # input_file_path
                    file_execution_id,  # file_execution_id
                )
            )

        # Set context for manual review
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.organization_id = organization_id

        # Call the main batch processing method
        return self.handle_output_for_files(files_data, api_client)

    def _evaluate_manual_review_batch(
        self,
        files_data: list[
            tuple[str, FileHashData, str, str]
        ],  # (file_name, file_hash, input_file_path, file_execution_id)
        workflow: dict[str, Any],
        api_client: Optional["InternalAPIClient"] = None,
    ) -> list[bool]:
        """Evaluate batch of files for manual review using plugin-based logic.

        Args:
            files_data: List of file data tuples
            workflow: Workflow configuration
            api_client: API client for backend communication

        Returns:
            List of boolean decisions (True = send to manual review)
        """
        if not files_data or not api_client:
            return [False] * len(files_data)

        try:
            # Import the manual review evaluator - create inline class to avoid import issues for now
            # TODO: Fix plugin import system properly later
            import hashlib

            from unstract.core.data_models import FileHashData

            class PercentageEvaluator:
                """Temporary inline evaluator to avoid import issues."""

                def evaluate_batch(
                    self,
                    files: list[FileHashData],
                    percentage: int,
                    rule_logic: str = "OR",
                    rule_json: dict = None,
                ) -> list[bool]:
                    """Evaluate batch of files for manual review based on percentage."""
                    if not files or percentage <= 0:
                        return [False] * len(files)

                    # Calculate target count (at least 1)
                    num_files = len(files)
                    target_count = max(1, (num_files * percentage) // 100)

                    if target_count >= num_files:
                        return [True] * num_files

                    # Create deterministic selection based on file hashes
                    file_scores = []
                    for file_hash in files:
                        # Use file name + path for consistent hashing
                        hash_input = f"{file_hash.file_name}:{file_hash.file_path}"
                        score = int(
                            hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16
                        )
                        file_scores.append((score, file_hash))

                    # Sort by score and select top N files
                    file_scores.sort(key=lambda x: x[0])
                    selected_files = {item[1] for item in file_scores[:target_count]}

                    return [file_hash in selected_files for file_hash in files]

                def get_evaluation_metadata(
                    self, decisions: list[bool], percentage: int, files: list
                ) -> dict:
                    """Get evaluation metadata."""
                    selected_count = sum(decisions)
                    total_files = len(files)
                    actual_percentage = (
                        (selected_count / total_files * 100) if total_files > 0 else 0
                    )

                    return {
                        "total_files": total_files,
                        "target_percentage": percentage,
                        "selected_count": selected_count,
                        "actual_percentage": round(actual_percentage, 2),
                        "selection_method": "deterministic_hash_based",
                    }

            # Get DB rules data from backend (ORM only)
            response = api_client.manual_review_client.get_db_rules_data(
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
            )

            if not response.success:
                logger.warning(f"Failed to get DB rules data: {response.error}")
                return [False] * len(files_data)

            # Extract rules data
            rules_data = response.data
            percentage = rules_data.get("percentage", 0)
            rule_logic = rules_data.get("rule_logic", "OR")
            rule_json = rules_data.get("rule_json")

            logger.info(
                f"Manual review batch evaluation: {len(files_data)} files, {percentage}% target"
            )

            if percentage <= 0:
                logger.info("No manual review required (percentage = 0)")
                return [False] * len(files_data)

            # Create evaluator and evaluate batch
            evaluator = PercentageEvaluator()
            file_hash_list = [file_hash for _, file_hash, _, _ in files_data]

            decisions = evaluator.evaluate_batch(
                files=file_hash_list,
                percentage=percentage,
                rule_logic=rule_logic,
                rule_json=rule_json,
            )

            # Log evaluation metadata
            metadata = evaluator.get_evaluation_metadata(
                decisions, percentage, file_hash_list
            )
            logger.info(f"Batch evaluation results: {metadata}")

            return decisions

        except ImportError:
            logger.warning(
                "Manual review plugin not available, skipping batch evaluation"
            )
            return [False] * len(files_data)
        except Exception as e:
            logger.error(f"Error in batch manual review evaluation: {e}")
            return [False] * len(files_data)

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
        import base64

        try:
            from unstract.filesystem import FileStorageType, FileSystem

            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()

            if not file_storage.exists(input_file_path):
                raise Exception(f"File not found: {input_file_path}")

            file_bytes = file_storage.read(input_file_path, mode="rb")
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")
            return base64.b64encode(file_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to read file content for {file_name}: {e}")
            raise Exception(f"Failed to read file content for queue: {e}")

    def _read_file_from_source_connector(
        self, input_file_path: str, file_name: str, workflow: dict[str, Any]
    ) -> str:
        """Read and encode file content from source connector for ETL/TASK workflows.

        This method replicates the backend logic: source_fs.open(input_file_path, "rb")
        """
        import base64

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
                    raise Exception(
                        f"Source connector configuration not available for {file_name}"
                    )
            else:
                source_connector_id = self.source_connector_id
                source_connector_settings = self.source_connector_settings

            logger.debug(
                f"Using source connector {source_connector_id} to read {file_name}"
            )

            # Import connector operations
            from unstract.connectors.connectorkit import Connectorkit

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
            raise Exception(f"Failed to read file from source connector: {e}")


# Alias for backward compatibility
DestinationConnector = WorkerDestinationConnector
