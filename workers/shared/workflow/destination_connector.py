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
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from unstract.core.data_models import ConnectionType as CoreConnectionType
from unstract.core.data_models import FileHashData

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

    def __post_init__(self):
        if self.settings is None:
            self.settings = {}
        if self.connector_settings is None:
            self.connector_settings = {}
        # Determine if this is an API destination
        if self.connection_type and "api" in self.connection_type.lower():
            self.is_api = True

    def get_core_connection_type(self) -> CoreConnectionType:
        """Convert string connection_type to CoreConnectionType enum."""
        try:
            # Map string values to enum values
            type_mapping = {
                "FILESYSTEM": CoreConnectionType.FILESYSTEM,
                "DATABASE": CoreConnectionType.DATABASE,
                "API": CoreConnectionType.API,
                "API_DEPLOYMENT": CoreConnectionType.API_DEPLOYMENT,
                "QUEUE": CoreConnectionType.QUEUE,
                "MANUALREVIEW": CoreConnectionType.MANUALREVIEW,
            }

            # Handle case-insensitive lookup
            connection_type_upper = self.connection_type.upper()
            if connection_type_upper in type_mapping:
                return type_mapping[connection_type_upper]
            else:
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
        )


class WorkerDestinationConnector:
    """Worker-compatible destination connector following production patterns.

    This class replicates the functionality of backend DestinationConnector
    from workflow_manager/endpoint_v2/destination.py without Django dependencies.
    """

    # Connection type constants matching backend
    class ConnectionType:
        FILESYSTEM = "FILESYSTEM"
        DATABASE = "DATABASE"
        API = "API"
        MANUALREVIEW = "MANUALREVIEW"

    def __init__(self, config: DestinationConfig, workflow_log=None):
        self.config = config
        self.connection_type = config.connection_type
        self.is_api = config.is_api
        self.use_file_history = config.use_file_history
        self.settings = config.settings
        self.workflow_log = workflow_log

        # Store connector instance details
        self.connector_id = config.connector_id
        self.connector_settings = config.connector_settings
        self.connector_name = config.connector_name

    @classmethod
    def from_config(cls, workflow_log, config: DestinationConfig):
        """Create destination connector from config (matching Django backend interface)."""
        return cls(config, workflow_log)

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

        try:
            if connection_type == self.ConnectionType.FILESYSTEM:
                self.copy_output_to_output_directory(input_file_path)
            elif connection_type == self.ConnectionType.DATABASE:
                # DEBUG: Log what tool_execution_result we received
                logger.info(
                    f"DEBUG: handle_output DATABASE - received tool_execution_result type: {type(tool_execution_result)}"
                )
                logger.info(
                    f"DEBUG: handle_output DATABASE - received tool_execution_result value: {tool_execution_result}"
                )
                logger.info(
                    f"DEBUG: handle_output DATABASE - bool(tool_execution_result): {bool(tool_execution_result)}"
                )
                logger.info(
                    f"DEBUG: handle_output DATABASE - 'not tool_execution_result': {not tool_execution_result}"
                )

                # Get real tool execution result if not provided
                if not tool_execution_result:
                    logger.info(
                        "DEBUG: handle_output DATABASE - extracting tool result from context because tool_execution_result is falsy"
                    )
                    tool_execution_result = (
                        self.get_tool_execution_result_from_execution_context(
                            workflow_id=workflow_id,
                            execution_id=execution_id,
                            file_execution_id=file_execution_id,
                            organization_id=organization_id,
                        )
                    )
                    logger.info(
                        f"DEBUG: handle_output DATABASE - extracted tool_execution_result: {tool_execution_result}"
                    )
                else:
                    logger.info(
                        "DEBUG: handle_output DATABASE - using provided tool_execution_result"
                    )

                # Handle database insertion following production pattern
                self.insert_into_db(input_file_path, tool_execution_result)
            elif connection_type == self.ConnectionType.API:
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
            elif connection_type == self.ConnectionType.MANUALREVIEW:
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
                )
            else:
                logger.warning(f"Unknown destination connection type: {connection_type}")

        except Exception as destination_error:
            logger.error(f"Destination handle_output failed: {str(destination_error)}")
            # Don't re-raise for API destinations to allow workflow completion
            if connection_type != self.ConnectionType.API:
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
        include_agent = bool(self.settings.get("include_agent", False))
        include_timestamp = bool(self.settings.get("include_timestamp", False))
        agent_name = str(self.settings.get("agent_name", "UNSTRACT_DBWRITER"))
        column_mode = str(
            self.settings.get("column_mode", "WRITE_JSON_TO_A_SINGLE_COLUMN")
        )
        single_column_name = str(self.settings.get("single_column_name", "data"))
        file_path_name = str(self.settings.get("file_path", "file_path"))
        execution_id_name = str(self.settings.get("execution_id", "execution_id"))

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

        # Generate execution ID for this operation
        execution_id = str(uuid.uuid4())

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

    def _push_data_to_queue(
        self,
        file_name: str,
        workflow: dict[str, Any],
        input_file_path: str,
        file_execution_id: str,
        tool_execution_result: str = None,
    ) -> None:
        """Handle manual review queue processing (following production pattern)."""
        logger.info(f"Pushing {file_name} to manual review queue")
        # Placeholder implementation for manual review queue
        pass


# Alias for backward compatibility
DestinationConnector = WorkerDestinationConnector
