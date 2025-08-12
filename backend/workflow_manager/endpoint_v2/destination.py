import ast
import base64
import json
import logging
import os
from typing import Any

from connector_v2.models import ConnectorInstance
from plugins.workflow_manager.workflow_v2.utils import WorkflowUtil
from rest_framework.exceptions import APIException
from usage_v2.helper import UsageHelper
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.base_connector import BaseConnector
from workflow_manager.endpoint_v2.constants import (
    ApiDeploymentResultStatus,
    DestinationKey,
)
from workflow_manager.endpoint_v2.database_utils import DatabaseUtils
from workflow_manager.endpoint_v2.dto import DestinationConfig, FileHash
from workflow_manager.endpoint_v2.exceptions import (
    DestinationConnectorNotConfigured,
    InvalidDestinationConnectionType,
    InvalidToolOutputType,
    MissingDestinationConnectionType,
    ToolOutputTypeMismatch,
)
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.endpoint_v2.queue_utils import (
    QueueResult,
    QueueResultStatus,
    QueueUtils,
)
from workflow_manager.utils.workflow_log import WorkflowLog
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

from backend.exceptions import UnstractFSException
from unstract.connectors.exceptions import ConnectorError
from unstract.filesystem import FileStorageType, FileSystem
from unstract.sdk.constants import ToolExecKey
from unstract.sdk.tool.mime_types import EXT_MIME_MAP
from unstract.workflow_execution.constants import ToolOutputType

logger = logging.getLogger(__name__)


class DestinationConnector(BaseConnector):
    """A class representing a Destination connector for a workflow.

    This class extends the BaseConnector class and provides methods for
    interacting with different types of destination connectors,
    such as file system connectors and API connectors and DB connectors.

    Attributes:
        workflow (Workflow): The workflow associated with
            the destination connector.
    """

    def __init__(
        self,
        workflow: Workflow,
        execution_id: str,
        workflow_log: WorkflowLog,
        use_file_history: bool,
        file_execution_id: str | None = None,
        hitl_queue_name: str | None = None,
    ) -> None:
        """Initialize a DestinationConnector object.

        Args:
            workflow (Workflow): _description_
        """
        organization_id = UserContext.get_organization_identifier()
        super().__init__(workflow.id, execution_id, organization_id, file_execution_id)
        self.endpoint = self._get_endpoint_for_workflow(workflow=workflow)
        self.source_endpoint = self._get_source_endpoint_for_workflow(workflow=workflow)
        self.execution_id = execution_id
        self.queue_results: list[dict[str, Any]] = []
        self.is_api: bool = (
            self.endpoint.connection_type == WorkflowEndpoint.ConnectionType.API
        )
        self.workflow_log = workflow_log
        self.use_file_history = use_file_history
        self.hitl_queue_name = hitl_queue_name
        self.workflow = workflow

    def _get_endpoint_for_workflow(
        self,
        workflow: Workflow,
    ) -> WorkflowEndpoint:
        """Get WorkflowEndpoint instance.

        Args:
            workflow (Workflow): Workflow associated with the
                destination connector.

        Returns:
            WorkflowEndpoint: WorkflowEndpoint instance.
        """
        endpoint: WorkflowEndpoint = WorkflowEndpoint.objects.get(
            workflow=workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
        )
        return endpoint

    def _get_source_endpoint_for_workflow(
        self,
        workflow: Workflow,
    ) -> WorkflowEndpoint:
        """Get WorkflowEndpoint instance.

        Args:
            workflow (Workflow): Workflow associated with the
                destination connector.

        Returns:
            WorkflowEndpoint: WorkflowEndpoint instance.
        """
        endpoint: WorkflowEndpoint = WorkflowEndpoint.objects.get(
            workflow=workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
        )
        return endpoint

    def validate(self) -> None:
        connection_type = self.endpoint.connection_type
        connector: ConnectorInstance = self.endpoint.connector_instance
        if connection_type is None:
            raise MissingDestinationConnectionType()
        if connection_type not in WorkflowEndpoint.ConnectionType.values:
            raise InvalidDestinationConnectionType()
        if (
            connection_type != WorkflowEndpoint.ConnectionType.API
            and connection_type != WorkflowEndpoint.ConnectionType.MANUALREVIEW
            and connector is None
        ):
            raise DestinationConnectorNotConfigured()

        # Validate database connection if it's a database destination
        if connection_type == WorkflowEndpoint.ConnectionType.DATABASE and connector:
            try:
                # Get database class and test connection
                db_class = DatabaseUtils.get_db_class(
                    connector_id=connector.connector_id,
                    connector_settings=connector.connector_metadata,
                )
                engine = db_class.get_engine()
                if hasattr(engine, "close"):
                    engine.close()
            except Exception as e:
                logger.error(f"Database connection failed: {str(e)}")
                raise

    def _should_handle_hitl(
        self,
        file_name: str,
        file_hash: FileHash,
        workflow: Workflow,
        input_file_path: str,
        file_execution_id: str,
    ) -> bool:
        """Determines if HITL processing should be performed, returning True if data was pushed to the queue."""
        # Check if API deployment requested HITL override
        if self.hitl_queue_name:
            logger.info(f"API HITL override: pushing to queue for file {file_name}")
            self._push_data_to_queue(
                file_name=file_name,
                workflow=workflow,
                input_file_path=input_file_path,
                file_execution_id=file_execution_id,
            )
            logger.info(f"Successfully pushed {file_name} to HITL queue")
            return True

        # Skip HITL validation if we're using file_history and no execution result is available
        if self.is_api and self.use_file_history:
            return False

        # Otherwise use existing workflow-based HITL logic
        execution_result = self.get_tool_execution_result()
        
        if WorkflowUtil.validate_db_rule(
            execution_result, workflow, file_hash.file_destination
        ):
            self._push_data_to_queue(
                file_name=file_name,
                workflow=workflow,
                input_file_path=input_file_path,
                file_execution_id=file_execution_id,
            )
            return True
            
        return False

    def _push_data_to_queue(
        self,
        file_name: str,
        workflow: Workflow,
        input_file_path: str,
        file_execution_id: str,
    ) -> None:
        result = self.get_tool_execution_result()
        meta_data = self.get_metadata()
        self._push_to_queue(
            file_name=file_name,
            workflow=workflow,
            result=result,
            input_file_path=input_file_path,
            meta_data=meta_data,
            file_execution_id=file_execution_id,
        )

    def handle_output(
        self,
        file_name: str,
        file_hash: FileHash,
        file_history: FileHistory | None,
        workflow: Workflow,
        input_file_path: str,
        file_execution_id: str = None,
        error: str | None = None,
    ) -> str | None:
        """Handle the output based on the connection type."""
        connection_type = self.endpoint.connection_type
        tool_execution_result: str | None = None

        if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
            self.copy_output_to_output_directory()
            
        elif connection_type == WorkflowEndpoint.ConnectionType.DATABASE:
            # For error cases, skip HITL and directly insert error record
            if error:
                self.insert_into_db(input_file_path=input_file_path, error=error)
            else:
                # For success cases, check HITL first, then insert if not HITL
                if not self._should_handle_hitl(
                    file_name=file_name,
                    file_hash=file_hash,
                    workflow=workflow,
                    input_file_path=input_file_path,
                    file_execution_id=file_execution_id,
                ):
                    self.insert_into_db(input_file_path=input_file_path, error=error)
                    
        elif connection_type == WorkflowEndpoint.ConnectionType.API:
            logger.info(f"API connection type detected for file {file_name}")
            # Check for HITL (Manual Review Queue) override for API deployments
            if not self._should_handle_hitl(
                file_name=file_name,
                file_hash=file_hash,
                workflow=workflow,
                input_file_path=input_file_path,
                file_execution_id=file_execution_id,
            ):
                logger.info(
                    f"No HITL override, getting tool execution result for {file_name}"
                )
                tool_execution_result = self.get_tool_execution_result(file_history)
                
        elif connection_type == WorkflowEndpoint.ConnectionType.MANUALREVIEW:
            self._push_data_to_queue(
                file_name,
                workflow,
                input_file_path,
                file_execution_id,
            )
            
        self.workflow_log.publish_log(
            message=f"File '{file_name}' processed successfully"
        )
        return tool_execution_result

    def copy_output_to_output_directory(self) -> None:
        """Copy output to the destination directory."""
        connector: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector.connector_metadata
        destination_configurations: dict[str, Any] = self.endpoint.configuration
        root_path = str(connector_settings.get(DestinationKey.PATH, ""))

        output_directory = str(
            destination_configurations.get(DestinationKey.OUTPUT_FOLDER, "/")
        )
        destination_fs = self.get_fs_connector(
            settings=connector_settings, connector_id=connector.connector_id
        )
        output_directory = destination_fs.get_connector_root_dir(
            input_dir=output_directory, root_path=root_path
        )
        logger.debug(f"destination output directory {output_directory}")
        destination_volume_path = os.path.join(
            self.file_execution_dir, ToolExecKey.OUTPUT_DIR
        )

        try:
            destination_fs.create_dir_if_not_exists(input_dir=output_directory)
            # Traverse local directory and create the same structure in the
            # output_directory
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            fs = file_system.get_file_storage()
            dir_path = fs.walk(str(destination_volume_path))

            for root, dirs, files in dir_path:
                for dir_name in dirs:
                    current_dir = os.path.join(
                        output_directory,
                        os.path.relpath(root, destination_volume_path),
                        dir_name,
                    )
                    destination_fs.create_dir_if_not_exists(input_dir=current_dir)

                for file_name in files:
                    source_path = os.path.join(root, file_name)
                    destination_path = os.path.join(
                        output_directory,
                        os.path.relpath(root, destination_volume_path),
                        file_name,
                    )
                    destination_fs.upload_file_to_storage(
                        source_path=source_path, destination_path=destination_path
                    )
        except ConnectorError as e:
            raise UnstractFSException(core_err=e) from e

    def insert_into_db(self, input_file_path: str, error: str | None) -> None:
        """Insert data into the database."""
        connector_instance: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector_instance.connector_metadata
        destination_configurations: dict[str, Any] = self.endpoint.configuration
        table_name: str = str(destination_configurations.get(DestinationKey.TABLE))
        include_agent: bool = bool(
            destination_configurations.get(DestinationKey.INCLUDE_AGENT, False)
        )
        include_timestamp = bool(
            destination_configurations.get(DestinationKey.INCLUDE_TIMESTAMP, False)
        )
        agent_name = str(destination_configurations.get(DestinationKey.AGENT_NAME))
        column_mode = str(destination_configurations.get(DestinationKey.COLUMN_MODE))
        single_column_name = str(
            destination_configurations.get(DestinationKey.SINGLE_COLUMN_NAME, "data")
        )
        file_path_name = str(
            destination_configurations.get(DestinationKey.FILE_PATH, "file_path")
        )
        execution_id_name = str(
            destination_configurations.get(DestinationKey.EXECUTION_ID, "execution_id")
        )

        data = self.get_tool_execution_result()
        metadata = self.get_combined_metadata()

        # If no data and no error, don't execute CREATE or INSERT query
        if not data:
            logger.info("No data obtained from tool to insert into destination DB.")
            return

        # Remove metadata from result
        # Tool text-extractor returns data in the form of string.
        # Don't pop out metadata in this case.
        if isinstance(data, dict):
            data.pop("metadata", None)

        db_class = DatabaseUtils.get_db_class(
            connector_id=connector_instance.connector_id,
            connector_settings=connector_settings,
        )

        engine = db_class.get_engine()

        table_info = db_class.get_information_schema(table_name=table_name)

        # Check whether to migrate table to include new columns
        if table_info:
            is_string = db_class.is_string_column(
                table_info=table_info, column_name=single_column_name
            )
            if is_string:
                db_class.migrate_table_to_v2(
                    table_name=table_name,
                    column_name=single_column_name,
                    engine=engine,
                )

        values = DatabaseUtils.get_columns_and_values(
            column_mode_str=column_mode,
            data=data,
            metadata=metadata,
            include_timestamp=include_timestamp,
            include_agent=include_agent,
            agent_name=agent_name,
            single_column_name=single_column_name,
            file_path_name=file_path_name,
            execution_id_name=execution_id_name,
            table_info=table_info,
            file_path=input_file_path,
            execution_id=self.execution_id,
            error=error,
        )
        
        engine = None
        try:
            db_class = DatabaseUtils.get_db_class(
                connector_id=connector_instance.connector_id,
                connector_settings=connector_settings,
            )

            engine = db_class.get_engine()
            
            DatabaseUtils.create_table_if_not_exists(
                db_class=db_class,
                engine=engine,
                table_name=table_name,
                database_entry=values,
            )

            sql_columns_and_values = DatabaseUtils.get_sql_query_data(
                conn_cls=db_class,
                table_name=table_name,
                values=values,
            )

            DatabaseUtils.execute_write_query(
                db_class=db_class,
                engine=engine,
                table_name=table_name,
                sql_keys=list(sql_columns_and_values.keys()),
                sql_values=list(sql_columns_and_values.values()),
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

    def _handle_api_result(
        self,
        file_name: str,
        error: str | None = None,
        result: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Handle the API result.

        This method is responsible for handling the API result.
        It appends the file name and result to the 'results' list for API resp.

        Args:
            file_name (str): The name of the file.
            result (Optional[str], optional): The result of the API call.
                Defaults to None.

        Returns:
            None
        """
        api_result: dict[str, Any] = {
            "file": file_name,
            "file_execution_id": self.file_execution_id,
        }
        if error:
            api_result.update(
                {"status": ApiDeploymentResultStatus.FAILED, "error": error}
            )
        else:
            if result:
                api_result.update(
                    {
                        "status": ApiDeploymentResultStatus.SUCCESS,
                        "result": result,
                        "metadata": metadata,
                    }
                )
            else:
                api_result.update(
                    {"status": ApiDeploymentResultStatus.SUCCESS, "result": ""}
                )
        self.update_api_results(api_result)

    def parse_string(self, original_string: str) -> Any:
        """Parse the given string, attempting to evaluate it as a Python
        literal.
        ex: a json string to dict method
        Parameters:
        - original_string (str): The input string to be parsed.

        Returns:
        - Any: The parsed result. If the string can be evaluated as a Python
          literal, the result of the evaluation is returned.
          If not, the original string is returned unchanged.

        Note:
        This function uses `ast.literal_eval` to attempt parsing the string as a
        Python literal. If parsing fails due to a SyntaxError or ValueError,
        the original string is returned.

        Example:
        >>> parser.parse_string("42")
        42
        >>> parser.parse_string("[1, 2, 3]")
        [1, 2, 3]
        >>> parser.parse_string("Hello, World!")
        'Hello, World!'
        """
        try:
            # Try to evaluate as a Python literal
            python_literal = ast.literal_eval(original_string)
            return python_literal
        except (SyntaxError, ValueError):
            # If evaluating as a Python literal fails,
            # assume it's a plain string
            return original_string

    def get_tool_execution_result(
        self, file_history: FileHistory | None = None
    ) -> Any | None:
        """Get result data from the output file.

        Returns:
            Union[dict[str, Any], str]: Result data.
        """
        return self.get_tool_execution_result_from_metadata(file_history=file_history)

    def get_tool_execution_result_from_metadata(
        self, file_history: FileHistory | None = None
    ) -> Any | None:
        """Get result data from the output file.

        Returns:
            Union[dict[str, Any], str]: Result data.
        """
        if file_history and file_history.result:
            return self.parse_string(file_history.result)
        output_file = self.infile
        metadata: dict[str, Any] = self.get_workflow_metadata()
        output_type = self.get_output_type(metadata)
        result: dict[str, Any] | str = ""
        file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        file_storage = file_system.get_file_storage()
        try:
            # TODO: SDK handles validation; consider removing here.
            file_type = file_storage.mime_type(path=output_file)
            if output_type == ToolOutputType.JSON:
                if file_type != EXT_MIME_MAP[ToolOutputType.JSON.lower()]:
                    msg = f"Expected tool output type: JSON, got: '{file_type}'"
                    logger.error(msg)
                    raise ToolOutputTypeMismatch(detail=msg)
                file_content = file_storage.read(output_file, mode="r")
                result = json.loads(file_content)
            elif output_type == ToolOutputType.TXT:
                if file_type == EXT_MIME_MAP[ToolOutputType.JSON.lower()]:
                    msg = f"Expected tool output type: TXT, got: '{file_type}'"
                    logger.error(msg)
                    raise ToolOutputTypeMismatch(detail=msg)
                file_content = file_storage.read(output_file, mode="r")
                result = file_content.encode("utf-8").decode("unicode-escape")
            else:
                raise InvalidToolOutputType()
        except (FileNotFoundError, json.JSONDecodeError) as err:
            msg = f"Error while getting result from the tool: {err}"
            logger.error(msg)
            raise APIException(detail=msg)

        return result

    def has_valid_metadata(self, metadata: Any) -> bool:
        # Check if metadata is not None and metadata is a non-empty string
        if not metadata:
            return False
        if not isinstance(metadata, str):
            return False
        if metadata.strip().lower() == "none":
            return False
        return True

    def get_metadata(
        self, file_history: FileHistory | None = None
    ) -> dict[str, Any] | None:
        """Get metadata from the output file.

        Returns:
            Union[dict[str, Any], str]: Metadata.
        """
        if file_history:
            if self.has_valid_metadata(file_history.metadata):
                return self.parse_string(file_history.metadata)
            else:
                return None
        metadata: dict[str, Any] = self.get_workflow_metadata()

        return metadata

    def get_combined_metadata(self) -> dict[str, Any]:
        """Get combined workflow and usage metadata.

        Returns:
            dict[str, Any]: Combined metadata including workflow and usage data.
        """
        # Get workflow metadata
        workflow_metadata = self.get_metadata()

        # Get file_execution_id from metadata
        file_execution_id = workflow_metadata.get("file_execution_id")
        if not file_execution_id:
            return workflow_metadata

        usage_metadata = UsageHelper.get_aggregated_token_count(file_execution_id)

        # Combine both metadata
        workflow_metadata["usage"] = usage_metadata

        return workflow_metadata

    def delete_file_execution_directory(self) -> None:
        """Delete the file execution directory.

        Returns:
            None
        """
        file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        file_storage = file_system.get_file_storage()
        if self.file_execution_dir and file_storage.exists(self.file_execution_dir):
            file_storage.rm(self.file_execution_dir, recursive=True)

    @classmethod
    def delete_execution_and_api_storage_dir(
        cls, workflow_id: str, execution_id: str
    ) -> None:
        """Delete the execution and api storage directories.

        Returns:
            None
        """
        cls.delete_execution_directory(workflow_id, execution_id)
        cls.delete_api_storage_dir(workflow_id, execution_id)

    @classmethod
    def delete_api_storage_dir(cls, workflow_id: str, execution_id: str) -> None:
        """Delete the api storage path.

        Returns:
            None
        """
        api_storage_dir = cls.get_api_storage_dir_path(
            workflow_id=workflow_id, execution_id=execution_id
        )
        file_system = FileSystem(FileStorageType.API_EXECUTION)
        file_storage = file_system.get_file_storage()
        if file_storage.exists(api_storage_dir):
            file_storage.rm(api_storage_dir, recursive=True)
            logger.info(f"API storage directory deleted: {api_storage_dir}")

    @classmethod
    def delete_execution_directory(cls, workflow_id: str, execution_id: str) -> None:
        """Delete the execution directory.

        Returns:
            None
        """
        execution_dir = cls.get_execution_dir_path(
            workflow_id=workflow_id, execution_id=execution_id
        )
        file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        file_storage = file_system.get_file_storage()
        if file_storage.exists(execution_dir):
            file_storage.rm(execution_dir, recursive=True)
            logger.info(f"Execution directory deleted: {execution_dir}")

    @classmethod
    def create_endpoint_for_workflow(
        cls,
        workflow: Workflow,
    ) -> None:
        """Create a workflow endpoint for the destination.

        Args:
            workflow (Workflow): Workflow for which the endpoint is created.
        """
        endpoint = WorkflowEndpoint(
            workflow=workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
        )
        endpoint.save()

    @classmethod
    def get_json_schema_for_database(cls) -> dict[str, Any]:
        """Get JSON schema for the database.

        Returns:
            dict[str, Any]: JSON schema for the database.
        """
        schema_path = os.path.join(os.path.dirname(__file__), "static", "dest", "db.json")
        return cls.get_json_schema(file_path=schema_path)

    @classmethod
    def get_json_schema_for_file_system(cls) -> dict[str, Any]:
        """Get JSON schema for the file system.

        Returns:
            dict[str, Any]: JSON schema for the file system.
        """
        schema_path = os.path.join(
            os.path.dirname(__file__), "static", "dest", "file.json"
        )
        return cls.get_json_schema(file_path=schema_path)

    @classmethod
    def get_json_schema_for_api(cls) -> dict[str, Any]:
        """Json schema for api.

        Returns:
            dict[str, Any]: _description_
        """
        schema_path = os.path.join(
            os.path.dirname(__file__), "static", "dest", "api.json"
        )
        return cls.get_json_schema(file_path=schema_path)

    def get_config(self) -> DestinationConfig:
        """Get serializable configuration for the destination connector.

        Returns:
            DestinationConfig: Configuration containing all necessary data to reconstruct the connector
        """
        return DestinationConfig(
            workflow_id=self.workflow.id,
            execution_id=self.execution_id,
            use_file_history=self.use_file_history,
            hitl_queue_name=self.hitl_queue_name,
        )

    @classmethod
    def from_config(
        cls, workflow_log: WorkflowLog, config: DestinationConfig
    ) -> "DestinationConnector":
        """Create a DestinationConnector instance from configuration.

        Args:
            config (DestinationConfig): Configuration containing all necessary data to reconstruct the connector

        Returns:
            DestinationConnector: New instance
        """
        logger.info(
            f"Creating DestinationConnector from config: hitl_queue_name={config.hitl_queue_name}"
        )
        # Reconstruct workflow
        workflow = Workflow.objects.get(id=config.workflow_id)

        # Create destination connector instance
        destination = cls(
            workflow=workflow,
            execution_id=config.execution_id,
            workflow_log=workflow_log,
            use_file_history=config.use_file_history,
            file_execution_id=config.file_execution_id,
            hitl_queue_name=config.hitl_queue_name,
        )

        return destination

    def _get_review_queue_name(self) -> str:
        """Generate review queue name with optional HITL override for manual review processing.

        Returns:
            str: Queue name in the appropriate format:
                - Custom HITL queue: review_queue_{org}_{workflow_id}:{hitl_queue_name}
                - Standard queue: review_queue_{org}_{workflow_id}
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

    def _push_to_queue(
        self,
        file_name: str,
        workflow: Workflow,
        result: str | None = None,
        input_file_path: str | None = None,
        meta_data: dict[str, Any] | None = None,
        file_execution_id: str = None,
    ) -> None:
        """Handle the Manual Review QUEUE result.

        This method is responsible for pushing the input file and result to
        review queue.

        Args:
            file_name (str): The name of the file.
            workflow (Workflow): The workflow object containing
            details about the workflow.
            result (Optional[str], optional): The result of the API call.
                Defaults to None.
            input_file_path (Optional[str], optional):
            The path to the input file.
                Defaults to None.
            meta_data (Optional[dict[str, Any]], optional):
                A dictionary containing additional
                metadata related to the file. Defaults to None.

        Returns:
            None
        """
        if not result:
            return
        connector: ConnectorInstance = self.source_endpoint.connector_instance

        # For API deployments, use workflow execution storage instead of connector
        if self.is_api:
            logger.debug(
                f"API deployment detected for {file_name}, using workflow execution file system"
            )
            # For API deployments, read file content from workflow execution storage
            file_content_base64 = self._read_file_content_for_queue(
                input_file_path, file_name
            )

            # Use common queue naming method
            q_name = self._get_review_queue_name()
            whisper_hash = meta_data.get("whisper-hash") if meta_data else None

            queue_result = QueueResult(
                file=file_name,
                status=QueueResultStatus.SUCCESS,
                result=result,
                workflow_id=str(self.workflow_id),
                file_content=file_content_base64,
                whisper_hash=whisper_hash,
                file_execution_id=file_execution_id,
            ).to_dict()

            queue_result_json = json.dumps(queue_result)
            conn = QueueUtils.get_queue_inst()
            conn.enqueue(queue_name=q_name, message=queue_result_json)
            logger.info(f"Pushed {file_name} to queue {q_name} with file content")
            return

        connector_settings: dict[str, Any] = connector.connector_metadata

        source_fs = self.get_fsspec(
            settings=connector_settings, connector_id=connector.connector_id
        )
        with source_fs.open(input_file_path, "rb") as remote_file:
            whisper_hash = None
            file_content = remote_file.read()
            # Convert file content to a base64 encoded string
            file_content_base64 = base64.b64encode(file_content).decode("utf-8")

            # Use common queue naming method
            q_name = self._get_review_queue_name()
            if meta_data:
                whisper_hash = meta_data.get("whisper-hash")
            else:
                whisper_hash = None
            queue_result = QueueResult(
                file=file_name,
                status=QueueResultStatus.SUCCESS,
                result=result,
                workflow_id=str(self.workflow_id),
                file_content=file_content_base64,
                whisper_hash=whisper_hash,
                file_execution_id=file_execution_id,
            ).to_dict()
            # Convert the result dictionary to a JSON string
            queue_result_json = json.dumps(queue_result)
            conn = QueueUtils.get_queue_inst()
            # Enqueue the JSON string
            conn.enqueue(queue_name=q_name, message=queue_result_json)
            logger.info(f"Pushed {file_name} to queue {q_name} with file content")

    def _read_file_content_for_queue(self, input_file_path: str, file_name: str) -> str:
        """Read and encode file content for queue message.

        Args:
            input_file_path: Path to the file to read
            file_name: Name of the file for logging purposes

        Returns:
            Base64 encoded file content

        Raises:
            APIException: If file cannot be read or doesn't exist
        """
        try:
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()

            if not file_storage.exists(input_file_path):
                raise APIException(f"File not found: {input_file_path}")

            file_bytes = file_storage.read(input_file_path, mode="rb")
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")
            return base64.b64encode(file_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to read file content for {file_name}: {e}")
            raise APIException(f"Failed to read file content for queue: {e}")
