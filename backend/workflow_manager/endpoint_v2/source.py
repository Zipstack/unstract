import fnmatch
import logging
import os
import shutil
from hashlib import md5, sha256
from io import BytesIO
from typing import Any, Optional

import fsspec
from connector_processor.constants import ConnectorKeys
from connector_v2.models import ConnectorInstance
from django.core.files.uploadedfile import UploadedFile
from unstract.workflow_execution.enums import LogState
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.base_connector import BaseConnector
from workflow_manager.endpoint_v2.constants import (
    FilePattern,
    FileSystemConnector,
    FileType,
    SourceConstant,
    SourceKey,
    WorkflowFileType,
)
from workflow_manager.endpoint_v2.exceptions import (
    FileHashNotFound,
    InvalidInputDirectory,
    InvalidSourceConnectionType,
    MissingSourceConnectionType,
    OrganizationIdNotFound,
    SourceConnectorNotConfigured,
)
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


# TODO: Inherit from SourceConnector for different sources - File, API .etc.
class SourceConnector(BaseConnector):
    """A class representing a source connector for a workflow.

    This class extends the BaseConnector class and provides methods for
    interacting with different types of source connectors,
    such as file system connectors and API connectors.
    It allows listing files from the source connector,
    adding files to the execution volume, and retrieving JSON schemas for
    different types of connectors.

    Attributes:
        workflow (Workflow): The workflow associated with the source connector.
    """

    def __init__(
        self,
        workflow: Workflow,
        execution_id: str,
        organization_id: Optional[str] = None,
        execution_service: Optional[WorkflowExecutionServiceHelper] = None,
    ) -> None:
        """Initialize a SourceConnector object.

        Args:
            workflow (Workflow): _description_
        """
        organization_id = organization_id or UserContext.get_organization_identifier()
        if not organization_id:
            raise OrganizationIdNotFound()
        super().__init__(workflow.id, execution_id, organization_id)
        self.endpoint = self._get_endpoint_for_workflow(workflow=workflow)
        self.workflow = workflow
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.hash_value_of_file_content: Optional[str] = None
        self.execution_service = execution_service

    def _get_endpoint_for_workflow(
        self,
        workflow: Workflow,
    ) -> WorkflowEndpoint:
        """Get WorkflowEndpoint instance.

        Args:
            workflow (Workflow): Workflow

        Returns:
            WorkflowEndpoint: _description_
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
            raise MissingSourceConnectionType()
        if connection_type not in WorkflowEndpoint.ConnectionType.values:
            raise InvalidSourceConnectionType()
        if connection_type != WorkflowEndpoint.ConnectionType.API and connector is None:
            raise SourceConnectorNotConfigured()

    def valid_file_patterns(self, required_patterns: list[Any]) -> list[str]:
        patterns = {
            FileType.PDF_DOCUMENTS: FilePattern.PDF_DOCUMENTS,
            FileType.TEXT_DOCUMENTS: FilePattern.TEXT_DOCUMENTS,
            FileType.IMAGES: FilePattern.IMAGES,
        }
        wildcard = []
        if not required_patterns:
            wildcard.append("*")
        else:
            for pattern in required_patterns:
                wildcard.extend(patterns.get(pattern, []))
        return wildcard

    def list_file_from_api_storage(self) -> list[str]:
        """List all files from the api_storage_dir directory."""
        files: list[str] = []
        if not self.api_storage_dir:
            return files
        for file in os.listdir(self.api_storage_dir):
            file_path = os.path.join(self.api_storage_dir, file)
            if os.path.isfile(file_path):
                files.append(file_path)
        return files

    def list_files_from_file_connector(self) -> list[str]:
        """_summary_

        Raises:
            InvalidDirectory: _description_

        Returns:
            list[str]: _description_
        """
        connector: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector.connector_metadata
        source_configurations: dict[str, Any] = self.endpoint.configuration
        required_patterns = source_configurations.get(SourceKey.FILE_EXTENSIONS, [])
        recursive = bool(
            source_configurations.get(SourceKey.PROCESS_SUB_DIRECTORIES, False)
        )
        limit = int(
            source_configurations.get(
                SourceKey.MAX_FILES, FileSystemConnector.MAX_FILES
            )
        )
        root_dir_path = connector_settings.get(ConnectorKeys.PATH, "")

        input_directory = str(source_configurations.get(SourceKey.ROOT_FOLDER, ""))

        source_fs = self.get_fs_connector(
            settings=connector_settings, connector_id=connector.connector_id
        )
        input_directory = source_fs.get_connector_root_dir(
            input_dir=input_directory, root_path=root_dir_path
        )
        logger.debug(f"source input directory {input_directory}")
        if not isinstance(required_patterns, list):
            required_patterns = [required_patterns]

        source_fs_fsspec = source_fs.get_fsspec_fs()

        patterns = self.valid_file_patterns(required_patterns=required_patterns)
        is_directory = source_fs_fsspec.isdir(input_directory)
        if not is_directory:
            raise InvalidInputDirectory()
        matched_files = self._get_matched_files(
            source_fs_fsspec, input_directory, patterns, recursive, limit
        )
        self.publish_input_output_list_file_logs(input_directory, matched_files)
        return matched_files

    def publish_input_output_list_file_logs(
        self, input_directory: str, matched_files: list[str]
    ) -> None:
        if not self.execution_service:
            return None
        input_log = f"##Input folder:\n\n `{os.path.basename(input_directory)}`\n\n"
        self.execution_service.publish_update_log(
            state=LogState.INPUT_UPDATE, message=input_log
        )
        output_log = self._matched_files_component_log(matched_files)
        self.execution_service.publish_update_log(
            state=LogState.OUTPUT_UPDATE, message=output_log
        )

    def publish_input_file_content(self, input_file_path: str, input_text: str) -> None:
        if self.execution_service:
            output_log_message = f"##Input text:\n\n```text\n{input_text}\n```\n\n"
            input_log_message = (
                "##Input file:\n\n```text\n"
                f"{os.path.basename(input_file_path)}\n```\n\n"
            )
            self.execution_service.publish_update_log(
                state=LogState.INPUT_UPDATE, message=input_log_message
            )
            self.execution_service.publish_update_log(
                state=LogState.OUTPUT_UPDATE, message=output_log_message
            )

    def _matched_files_component_log(self, matched_files: list[str]) -> str:
        output_log = "### Matched files \n```text\n\n\n"
        for file in matched_files[:20]:
            output_log += f"{file}\n"
        output_log += "```\n\n"
        output_log += f"""Total matched files: {len(matched_files)}
            \n\nPlease note that only the first 20 files are shown.\n\n"""
        return output_log

    def _get_matched_files(
        self,
        source_fs: Any,
        input_directory: str,
        patterns: list[str],
        recursive: bool,
        limit: int,
    ) -> list[str]:
        """Get a list of matched files based on patterns in a directory.

        This method searches for files in the specified `input_directory` that
        match any of the given `patterns`.
        The search can be performed recursively if `recursive` is set to True.
        The number of matched files returned is limited by `limit`.

        Args:
            source_fs (Any): The file system object used for searching.
            input_directory (str): The directory to search for files.
            patterns (list[str]): The patterns to match against file names.
            recursive (bool): Whether to perform a recursive search.
            limit (int): The maximum number of matched files to return.

        Returns:
            list[str]: A list of matched file paths.
        """
        matched_files = []
        count = 0
        max_depth = int(SourceConstant.MAX_RECURSIVE_DEPTH) if recursive else 1

        for root, dirs, files in source_fs.walk(input_directory, maxdepth=max_depth):
            if count >= limit:
                break
            for file in files:
                if not file:
                    continue
                if count >= limit:
                    break
                if any(fnmatch.fnmatch(file, pattern) for pattern in patterns):
                    file_path = os.path.join(root, file)
                    file_path = f"{file_path}"
                    matched_files.append(file_path)
                    count += 1

        return matched_files

    def list_files_from_source(self) -> list[str]:
        """List files from source connector.

        Args:
            api_storage_dir (Optional[str], optional): API storage directory
        Returns:
            list[str]: list of files
        """
        connection_type = self.endpoint.connection_type
        if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
            return self.list_files_from_file_connector()
        elif connection_type == WorkflowEndpoint.ConnectionType.API:
            return self.list_file_from_api_storage()
        raise InvalidSourceConnectionType()

    @classmethod
    def hash_str(cls, string_to_hash: Any, hash_method: str = "sha256") -> str:
        """Computes the hash for a given input string.

        Useful to hash strings needed for caching and other purposes.
        Hash method defaults to "md5"

        Args:
            string_to_hash (str): String to be hashed
            hash_method (str): Hash hash_method to use, supported ones
                - "md5"

        Returns:
            str: Hashed string
        """
        if hash_method == "md5":
            if isinstance(string_to_hash, bytes):
                return str(md5(string_to_hash).hexdigest())
            return str(md5(string_to_hash.encode()).hexdigest())
        elif hash_method == "sha256":
            if isinstance(string_to_hash, (bytes, bytearray)):
                return str(sha256(string_to_hash).hexdigest())
            return str(sha256(string_to_hash.encode()).hexdigest())
        else:
            raise ValueError(f"Unsupported hash_method: {hash_method}")

    def add_input_from_connector_to_volume(self, input_file_path: str) -> str:
        """Add input file to execution directory.

        Args:
            input_file_path (str): The path of the input file.
        Returns:
            str: The hash value of the file content.
        Raises:
            FileHashNotFound: If the hash value of the file content
                is not found.
        """
        connector: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector.connector_metadata
        source_file_path = os.path.join(self.execution_dir, WorkflowFileType.SOURCE)
        infile_path = os.path.join(self.execution_dir, WorkflowFileType.INFILE)
        source_file = f"file://{source_file_path}"

        source_fs = self.get_fsspec(
            settings=connector_settings, connector_id=connector.connector_id
        )
        with (
            source_fs.open(input_file_path, "rb") as remote_file,
            fsspec.open(source_file, "wb") as local_file,
        ):
            file_content = remote_file.read()
            hash_value_of_file_content = self.hash_str(file_content)
            logger.info(
                f"hash_value_of_file {source_file} is "
                f": {hash_value_of_file_content}"
            )
            input_log = (
                file_content[:500].decode("utf-8", errors="replace") + "...(truncated)"
            )
            self.publish_input_file_content(input_file_path, input_log)

            local_file.write(file_content)
        shutil.copyfile(source_file_path, infile_path)
        logger.info(f"{input_file_path} is added in to execution directory")
        return hash_value_of_file_content

    def add_input_from_api_storage_to_volume(self, input_file_path: str) -> None:
        """Add input file to execution directory from api storage."""
        infile_path = os.path.join(self.execution_dir, WorkflowFileType.INFILE)
        source_path = os.path.join(self.execution_dir, WorkflowFileType.SOURCE)
        shutil.copyfile(input_file_path, infile_path)
        shutil.copyfile(input_file_path, source_path)

    def add_file_to_volume(
        self, input_file_path: str, hash_values_of_files: dict[str, str] = {}
    ) -> tuple[str, str]:
        """Add input file to execution directory.

        Args:
            input_file_path (str): source file

        Raises:
            InvalidSource: _description_

        Returns:
            str: file_name
        """
        connection_type = self.endpoint.connection_type
        file_name = os.path.basename(input_file_path)
        if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
            file_content_hash = self.add_input_from_connector_to_volume(
                input_file_path=input_file_path,
            )
        elif connection_type == WorkflowEndpoint.ConnectionType.API:
            self.add_input_from_api_storage_to_volume(input_file_path=input_file_path)
            if file_name not in hash_values_of_files:
                raise FileHashNotFound()
            file_content_hash = hash_values_of_files[file_name]
        else:
            raise InvalidSourceConnectionType()

        self.add_metadata_to_volume(
            input_file_path=input_file_path, source_hash=file_content_hash
        )
        return file_name, file_content_hash

    def handle_final_result(
        self,
        results: list[dict[str, Any]],
        file_name: str,
        result: Optional[str],
    ) -> None:
        connection_type = self.endpoint.connection_type
        if connection_type == WorkflowEndpoint.ConnectionType.API:
            results.append({"file": file_name, "result": result})

    def load_file(self, input_file_path: str) -> tuple[str, BytesIO]:
        """Load file contnt and file name based on the file path.

        Args:
            input_file_path (str): source file

        Raises:
            InvalidSource: _description_

        Returns:
            tuple[str, BytesIO]: file_name , file content
        """
        connector: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector.connector_metadata
        source_fs: fsspec.AbstractFileSystem = self.get_fsspec(
            settings=connector_settings, connector_id=connector.connector_id
        )
        with source_fs.open(input_file_path, "rb") as remote_file:
            file_content = remote_file.read()
            file_stream = BytesIO(file_content)

        return os.path.basename(input_file_path), file_stream

    @classmethod
    def add_input_file_to_api_storage(
        cls, workflow_id: str, execution_id: str, file_objs: list[UploadedFile]
    ) -> dict[str, str]:
        """Add input file to api storage.

        Args:
            workflow_id (str): UUID of the worklfow
            execution_id (str): UUID of the execution
            file_objs (list[UploadedFile]): List of uploaded files
        Returns:
            dict[str, FileHash]: Dict containing file name and its corresponding hash
        """
        api_storage_dir = cls.get_api_storage_dir_path(
            workflow_id=workflow_id, execution_id=execution_id
        )
        file_hashes: dict[str, str] = {}
        for file in file_objs:
            file_name = file.name
            destination_path = os.path.join(api_storage_dir, file_name)
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            with open(destination_path, "wb") as f:
                buffer = bytearray()
                for chunk in file.chunks():
                    buffer.extend(chunk)
                f.write(buffer)
            file_hashes.update({file_name: cls.hash_str(buffer)})
        return file_hashes

    @classmethod
    def create_endpoint_for_workflow(
        cls,
        workflow: Workflow,
    ) -> None:
        """Creating WorkflowEndpoint entity."""
        endpoint = WorkflowEndpoint(
            workflow=workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
        )
        endpoint.save()

    @classmethod
    def get_json_schema_for_api(cls) -> dict[str, Any]:
        """Json schema for api.

        Returns:
            dict[str, Any]: _description_
        """
        schema_path = os.path.join(
            os.path.dirname(__file__), "static", "src", "api.json"
        )
        return cls.get_json_schema(file_path=schema_path)

    @classmethod
    def get_json_schema_for_file_system(cls) -> dict[str, Any]:
        """Json schema for Filesystem.

        Returns:
            dict[str, Any]: _description_
        """
        schema_path = os.path.join(
            os.path.dirname(__file__), "static", "src", "file.json"
        )
        return cls.get_json_schema(file_path=schema_path)
