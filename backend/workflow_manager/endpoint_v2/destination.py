import ast
import base64
import json
import logging
import os
from typing import Any, Optional, Union

import fsspec
import magic
from connector_v2.models import ConnectorInstance
from fsspec.implementations.local import LocalFileSystem
from unstract.sdk.constants import ToolExecKey
from unstract.workflow_execution.constants import ToolOutputType
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.base_connector import BaseConnector
from workflow_manager.endpoint_v2.constants import (
    ApiDeploymentResultStatus,
    DestinationKey,
    QueueResultStatus,
    WorkflowFileType,
)
from workflow_manager.endpoint_v2.database_utils import DatabaseUtils
from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.endpoint_v2.exceptions import (
    DestinationConnectorNotConfigured,
    InvalidDestinationConnectionType,
    InvalidToolOutputType,
    MissingDestinationConnectionType,
    ToolOutputTypeMismatch,
)
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.endpoint_v2.queue_utils import QueueResult, QueueUtils
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.utils import WorkflowUtil

from backend.exceptions import UnstractFSException
from unstract.connectors.exceptions import ConnectorError

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
        execution_service: Optional[WorkflowExecutionServiceHelper] = None,
    ) -> None:
        """Initialize a DestinationConnector object.

        Args:
            workflow (Workflow): _description_
        """
        organization_id = UserContext.get_organization_identifier()
        super().__init__(workflow.id, execution_id, organization_id)
        self.endpoint = self._get_endpoint_for_workflow(workflow=workflow)
        self.source_endpoint = self._get_source_endpoint_for_workflow(workflow=workflow)
        self.execution_id = execution_id
        self.api_results: list[dict[str, Any]] = []
        self.queue_results: list[dict[str, Any]] = []
        self.execution_service = execution_service

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
        if endpoint.connector_instance:
            endpoint.connector_instance.connector_metadata = (
                endpoint.connector_instance.metadata
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
        if endpoint.connector_instance:
            endpoint.connector_instance.connector_metadata = (
                endpoint.connector_instance.metadata
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

    def _push_data_to_queue(
        self,
        file_name: str,
        workflow: Workflow,
        input_file_path: str,
    ) -> None:
        result = self.get_result()
        meta_data = self.get_metadata()
        self._push_to_queue(
            file_name=file_name,
            workflow=workflow,
            result=result,
            input_file_path=input_file_path,
            meta_data=meta_data,
        )

    def handle_output(
        self,
        file_name: str,
        file_hash: FileHash,
        workflow: Workflow,
        input_file_path: str,
        error: Optional[str] = None,
        use_file_history: bool = True,
    ) -> None:
        """Handle the output based on the connection type."""
        connection_type = self.endpoint.connection_type
        result: Optional[str] = None
        metadata: Optional[str] = None
        if error:
            if connection_type == WorkflowEndpoint.ConnectionType.API:
                self._handle_api_result(file_name=file_name, error=error, result=result)
            return

        file_history = None
        if use_file_history:
            file_history = FileHistoryHelper.get_file_history(
                workflow=workflow, cache_key=file_hash.file_hash
            )
        if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
            self.copy_output_to_output_directory()
        elif connection_type == WorkflowEndpoint.ConnectionType.DATABASE:
            result = self.get_result(file_history)
            if WorkflowUtil.db_rule_check(result, workflow, file_hash.file_destination):
                self._push_data_to_queue(file_name, workflow, input_file_path)
            else:
                self.insert_into_db(input_file_path=input_file_path)
        elif connection_type == WorkflowEndpoint.ConnectionType.API:
            result = self.get_result(file_history)
            exec_metadata = self.get_metadata(file_history)
            self._handle_api_result(
                file_name=file_name, error=error, result=result, metadata=exec_metadata
            )
        elif connection_type == WorkflowEndpoint.ConnectionType.MANUALREVIEW:
            self._push_data_to_queue(file_name, workflow, input_file_path)
        if self.execution_service:
            self.execution_service.publish_log(
                message=f"File '{file_name}' processed successfully"
            )

        if use_file_history and not file_history:
            FileHistoryHelper.create_file_history(
                cache_key=file_hash.file_hash,
                workflow=workflow,
                status=ExecutionStatus.COMPLETED,
                result=result,
                metadata=metadata,
                file_name=file_name,
            )

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
            self.execution_dir, ToolExecKey.OUTPUT_DIR
        )

        try:
            destination_fs.create_dir_if_not_exists(input_dir=output_directory)

            # Traverse local directory and create the same structure in the
            # output_directory
            for root, dirs, files in os.walk(destination_volume_path):
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

    def insert_into_db(self, input_file_path: str) -> None:
        """Insert data into the database."""
        connector_instance: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector_instance.metadata
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
        data = self.get_result()
        # If data is None, don't execute CREATE or INSERT query
        if not data:
            return

        # Remove metadata from result
        # Tool text-extractor returns data in the form of string.
        # Don't pop out metadata in this case.
        if isinstance(data, dict):
            data.pop("metadata", None)
        values = DatabaseUtils.get_columns_and_values(
            column_mode_str=column_mode,
            data=data,
            include_timestamp=include_timestamp,
            include_agent=include_agent,
            agent_name=agent_name,
            single_column_name=single_column_name,
            file_path_name=file_path_name,
            execution_id_name=execution_id_name,
            file_path=input_file_path,
            execution_id=self.execution_id,
        )
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
        cls_name = db_class.__class__.__name__
        sql_columns_and_values = DatabaseUtils.get_sql_query_data(
            cls_name=cls_name,
            connector_id=connector_instance.connector_id,
            connector_settings=connector_settings,
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

    def _handle_api_result(
        self,
        file_name: str,
        error: Optional[str] = None,
        result: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
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
        api_result: dict[str, Any] = {"file": file_name}
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
        self.api_results.append(api_result)

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

    def get_result(self, file_history: Optional[FileHistory] = None) -> Optional[Any]:
        """Get result data from the output file.

        Returns:
            Union[dict[str, Any], str]: Result data.
        """
        if file_history and file_history.result:
            return self.parse_string(file_history.result)
        output_file = os.path.join(self.execution_dir, WorkflowFileType.INFILE)
        metadata: dict[str, Any] = self.get_workflow_metadata()
        output_type = self.get_output_type(metadata)
        result: Union[dict[str, Any], str] = ""
        try:
            # TODO: SDK handles validation; consider removing here.
            mime = magic.Magic()
            file_type = mime.from_file(output_file)
            if output_type == ToolOutputType.JSON:
                if "JSON" not in file_type:
                    logger.error(f"Output type json mismatched {file_type}")
                    raise ToolOutputTypeMismatch()
                with open(output_file) as file:
                    result = json.load(file)
            elif output_type == ToolOutputType.TXT:
                if "JSON" in file_type:
                    logger.error(f"Output type txt mismatched {file_type}")
                    raise ToolOutputTypeMismatch()
                with open(output_file) as file:
                    result = file.read()
                    result = result.encode("utf-8").decode("unicode-escape")
            else:
                raise InvalidToolOutputType()
        except (FileNotFoundError, json.JSONDecodeError) as err:
            logger.error(f"Error while getting result {err}")
        return result

    def get_metadata(
        self, file_history: Optional[FileHistory] = None
    ) -> Optional[dict[str, Any]]:
        """Get metadata from the output file.

        Returns:
            Union[dict[str, Any], str]: Metadata.
        """
        if file_history and file_history.metadata:
            return self.parse_string(file_history.metadata)
        metadata: dict[str, Any] = self.get_workflow_metadata()

        return metadata

    def delete_execution_directory(self) -> None:
        """Delete the execution directory.

        Returns:
            None
        """
        fs: LocalFileSystem = fsspec.filesystem("file")
        fs.rm(self.execution_dir, recursive=True)
        self.delete_api_storage_dir(self.workflow_id, self.execution_id)

    @classmethod
    def delete_api_storage_dir(cls, workflow_id: str, execution_id: str) -> None:
        """Delete the api storage path.

        Returns:
            None
        """
        api_storage_dir = cls.get_api_storage_dir_path(
            workflow_id=workflow_id, execution_id=execution_id
        )
        fs: LocalFileSystem = fsspec.filesystem("file")
        fs.rm(api_storage_dir, recursive=True)

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
        schema_path = os.path.join(
            os.path.dirname(__file__), "static", "dest", "db.json"
        )
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

    def _push_to_queue(
        self,
        file_name: str,
        workflow: Workflow,
        result: Optional[str] = None,
        input_file_path: Optional[str] = None,
        meta_data: Optional[dict[str, Any]] = None,
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
        connector_settings: dict[str, Any] = connector.connector_metadata

        source_fs = self.get_fsspec(
            settings=connector_settings, connector_id=connector.connector_id
        )
        with source_fs.open(input_file_path, "rb") as remote_file:
            whisper_hash = None
            file_content = remote_file.read()
            # Convert file content to a base64 encoded string
            file_content_base64 = base64.b64encode(file_content).decode("utf-8")
            q_name = f"review_queue_{self.organization_id}_{workflow.id}"
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
            ).to_dict()
            # Convert the result dictionary to a JSON string
            queue_result_json = json.dumps(queue_result)
            conn = QueueUtils.get_queue_inst()
            # Enqueue the JSON string
            conn.enqueue(queue_name=q_name, message=queue_result_json)
