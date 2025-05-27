import fnmatch
import logging
import os
import shutil
from hashlib import sha256
from io import BytesIO
from itertools import islice
from typing import Any

import fsspec
from connector_processor.constants import ConnectorKeys
from connector_v2.models import ConnectorInstance
from django.core.files.uploadedfile import UploadedFile
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.base_connector import BaseConnector
from workflow_manager.endpoint_v2.constants import (
    FilePattern,
    FileSystemConnector,
    FileType,
    SourceConstant,
    SourceKey,
)
from workflow_manager.endpoint_v2.dto import FileHash, SourceConfig
from workflow_manager.endpoint_v2.exceptions import (
    InvalidInputDirectory,
    InvalidSourceConnectionType,
    MissingSourceConnectionType,
    OrganizationIdNotFound,
    SourceConnectorNotConfigured,
    SourceFileOrInfilePathNotFound,
)
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.utils.workflow_log import WorkflowLog
from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.filesystem import FileStorageType, FileSystem
from unstract.sdk.file_storage import FileStorage
from unstract.workflow_execution.enums import LogState

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

    READ_CHUNK_SIZE = 4194304  # Chunk size for reading files

    def __init__(
        self,
        workflow: Workflow,
        execution_id: str,
        workflow_log: WorkflowLog,
        use_file_history: bool,
        organization_id: str | None = None,
        file_execution_id: str | None = None,
    ) -> None:
        """Create a SourceConnector.

        Args:
            workflow (Workflow): Associated workflow instance
            execution_id (str): UUID of the current execution
            organization_id (Optional[str]): Organization ID. Defaults to None.
            execution_service (Optional[WorkflowExecutionServiceHelper]): Instance of
                WorkflowExecutionServiceHelper that helps with WF execution.
                Defaults to None. This is not used in case of execution by API.

        Raises:
            OrganizationIdNotFound: _description_
        """
        organization_id = organization_id or UserContext.get_organization_identifier()
        if not organization_id:
            raise OrganizationIdNotFound()
        super().__init__(workflow.id, execution_id, organization_id, file_execution_id)
        self.endpoint = self._get_endpoint_for_workflow(workflow=workflow)
        self.workflow = workflow
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.hash_value_of_file_content: str | None = None
        self.workflow_log = workflow_log
        self.use_file_history = use_file_history

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

    def list_file_from_api_storage(
        self, file_hashes: dict[str, FileHash]
    ) -> tuple[dict[str, FileHash], int]:
        """List all files from the api_storage_dir directory."""
        return file_hashes, len(file_hashes)

    def list_files_from_file_connector(self) -> tuple[dict[str, FileHash], int]:
        """_summary_

        Raises:
            InvalidDirectory: _description_

        Returns:
            tuple[dict[str, FileHash], int]: A dictionary of matched file paths
            and their corresponding FileHash objects, along with the total count
            of matched files.
        """
        connector: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector.connector_metadata
        source_configurations: dict[str, Any] = self.endpoint.configuration
        required_patterns = list(source_configurations.get(SourceKey.FILE_EXTENSIONS, []))
        recursive = bool(
            source_configurations.get(SourceKey.PROCESS_SUB_DIRECTORIES, False)
        )
        limit = int(
            source_configurations.get(SourceKey.MAX_FILES, FileSystemConnector.MAX_FILES)
        )
        root_dir_path = connector_settings.get(ConnectorKeys.PATH, "")
        folders_to_process = list(source_configurations.get(SourceKey.FOLDERS, ["/"]))
        # Process from root in case its user provided list is empty
        if not folders_to_process:
            folders_to_process = ["/"]
        patterns = self.valid_file_patterns(required_patterns=required_patterns)
        self.publish_user_sys_log(
            f"Matching for patterns '{', '.join(patterns)}' from "
            f"'{', '.join(folders_to_process)}'"
        )

        source_fs = self.get_fs_connector(
            settings=connector_settings, connector_id=connector.connector_id
        )
        source_fs_fsspec = source_fs.get_fsspec_fs()
        # Checking if folders exist at source before processing
        # TODO: Validate while receiving this input configuration as well
        for input_directory in folders_to_process:
            # TODO: Move to connector class for better error handling
            try:
                input_directory = source_fs.get_connector_root_dir(
                    input_dir=input_directory, root_path=root_dir_path
                )
                if not source_fs_fsspec.isdir(input_directory):
                    raise InvalidInputDirectory(dir=input_directory)
            except Exception as e:
                msg = f"Error while validating path '{input_directory}'. {str(e)}"
                self.publish_user_sys_log(msg)
                if isinstance(e, InvalidInputDirectory):
                    raise
                raise InvalidInputDirectory(detail=msg)

        total_files_to_process = 0
        total_matched_files = {}

        for input_directory in folders_to_process:
            input_directory = source_fs.get_connector_root_dir(
                input_dir=input_directory, root_path=root_dir_path
            )
            logger.debug(f"Listing files from:  {input_directory}")
            matched_files, count = self._get_matched_files(
                source_fs, input_directory, patterns, recursive, limit
            )
            self.publish_user_sys_log(f"Matched '{count}' files from '{input_directory}'")
            total_matched_files.update(matched_files)
            total_files_to_process += count
        self.publish_input_output_list_file_logs(
            folders_to_process, total_matched_files, total_files_to_process
        )
        return total_matched_files, total_files_to_process

    def publish_user_sys_log(self, msg: str) -> None:
        """Publishes log to the user and system.

        Pushes logs messages to the configured logger and to the
        websocket channel if the `execution_service` is configured.

        Args:
            msg (str): Message to log
        """
        logger.info(msg)
        self.workflow_log.publish_log(message=msg)

    def publish_input_output_list_file_logs(
        self, folders: list[str], matched_files: dict[str, FileHash], count: int
    ) -> None:
        folders_list = "\n".join(f"- `{folder.strip()}`" for folder in folders)
        input_log = f"## Folders to process:\n\n{folders_list}\n\n"
        self.workflow_log.publish_update_log(
            state=LogState.INPUT_UPDATE, message=input_log
        )
        output_log = self._matched_files_component_log(matched_files, count)
        self.workflow_log.publish_update_log(
            state=LogState.OUTPUT_UPDATE, message=output_log
        )

    def publish_input_file_content(self, input_file_path: str, input_text: str) -> None:
        output_log_message = f"## Input text:\n\n```text\n{input_text}\n```\n\n"
        input_log_message = (
            f"## Input file:\n\n```text\n{os.path.basename(input_file_path)}\n```\n\n"
        )
        self.workflow_log.publish_update_log(
            state=LogState.INPUT_UPDATE, message=input_log_message
        )
        self.workflow_log.publish_update_log(
            state=LogState.OUTPUT_UPDATE, message=output_log_message
        )

    def _matched_files_component_log(
        self, matched_files: dict[str, FileHash], count: int
    ) -> str:
        output_log = "### Matched files \n```text\n\n\n"
        for file_path in islice(matched_files.keys(), 20):
            output_log += f"- {file_path}\n"
        output_log += "```\n\n"
        output_log += f"""Total matched files: {count}
            \n\nPlease note that only the first 20 files are shown.\n\n"""
        return output_log

    def _get_matched_files(
        self,
        source_fs: UnstractFileSystem,
        input_directory: str,
        patterns: list[str],
        recursive: bool,
        limit: int,
    ) -> tuple[dict[str, FileHash], int]:
        """Get a dictionary of matched files based on patterns in a directory.

        This method searches for files in the specified `input_directory` that
        match any of the given `patterns`. The search can be performed recursively
        if `recursive` is set to True. The number of matched files returned is
        limited by `limit`.

        Args:
            source_fs (Any): The file system object used for searching.
            input_directory (str): The directory to search for files.
            patterns (list[str]): The patterns to match against file names.
            recursive (bool): Whether to perform a recursive search.
            limit (int): The maximum number of matched files to return.

        Returns:
            tuple[dict[str, FileHash], int]: A dictionary of matched file paths
            and their corresponding FileHash objects, along with the total count
            of matched files.
        """
        matched_files: dict[str, FileHash] = {}
        count = 0
        max_depth = int(SourceConstant.MAX_RECURSIVE_DEPTH) if recursive else 1
        fs_fsspec = source_fs.get_fsspec_fs()
        for root, dirs, files in fs_fsspec.walk(input_directory, maxdepth=max_depth):
            for file in files:
                if count >= limit:
                    break
                if self._should_process_file(file, patterns):
                    file_path = str(os.path.join(root, file))
                    if self._is_new_file(
                        file_path=file_path,
                        workflow=self.endpoint.workflow,
                        source_fs=source_fs,
                    ):
                        matched_files[file_path] = self._create_file_hash(
                            file_path=file_path,
                            source_fs=source_fs,
                        )
                        count += 1
        return matched_files, count

    def _should_process_file(self, file: str, patterns: list[str]) -> bool:
        """Check if the file should be processed based on the patterns.

        Args:
            file: The filename to check
            patterns: List of patterns to match against

        Returns:
            bool: True if file should be processed, False otherwise
        """
        if not file:
            return False

        file_lower = file.lower()
        matches_pattern = any(
            fnmatch.fnmatchcase(file_lower, pattern.lower()) for pattern in patterns
        )

        return matches_pattern and self._is_valid_pattern(file)

    def _is_valid_pattern(self, file_name: str) -> bool:
        """Check if the file has a supported format.

        Args:
            file_name: The filename to check

        Returns:
            bool: True if file format is supported, False otherwise
        """
        file_lower = file_name.lower()
        matches_blocked = any(
            fnmatch.fnmatchcase(file_lower, ext.lower())
            for ext in FilePattern.UNSUPPORTED_FILE_EXTENSIONS
        )

        if matches_blocked:
            message = f"Skipping '{file_name}' as it has an unsupported file format"
            logger.debug(message)
            self.workflow_log.publish_log(message)
            return False

        return True

    def _is_new_file(
        self, file_path: str, workflow: Workflow, source_fs: UnstractFileSystem
    ) -> bool:
        """Check if the file is new or already processed."""
        file_history = self._get_file_history(workflow, source_fs, file_path)
        # In case of ETL pipelines, its necessary to skip files which have
        # already been processed
        if self.use_file_history and file_history and file_history.is_completed():
            self.workflow_log.publish_log(
                f"Skipping file {file_path} as it has already been processed. "
                "Clear the file markers to process it again."
            )
            return False

        return True

    def _get_file_history(
        self, workflow: Workflow, source_fs: UnstractFileSystem, file_path: str
    ) -> FileHistory | None:
        """Retrieve file history using provider UUID or legacy cache key."""
        provider_file_uuid = source_fs.get_file_system_uuid(file_path)

        if provider_file_uuid:
            logger.info(f"Checking file history for provider UUID: {provider_file_uuid}")
            file_history = FileHistoryHelper.get_file_history(
                workflow=workflow, provider_file_uuid=provider_file_uuid
            )

            if file_history:
                return file_history  # Early return if history exists

            # The provider_file_uuid was recently integrated,
            # so we also check the cache_key for backward compatibility.
            # This ensures older files without a provider UUID
            # can still be identified.
            # In the future, this check can be removed as file history validation
            # is already handled during file execution.
            file_content_hash = self.get_file_content_hash(source_fs, file_path)
            logger.info(
                f"Checking file history for legacy cache key: {file_content_hash}"
            )
            file_history = FileHistoryHelper.get_file_history(
                workflow=workflow, cache_key=file_content_hash
            )

            if file_history and file_history.is_completed():
                file_history.update(provider_file_uuid=provider_file_uuid)

        # Fallback for connectors that do not support provider_file_uuid
        else:
            file_content_hash = self.get_file_content_hash(source_fs, file_path)
            logger.info(
                f"Checking file history for legacy cache key: {file_content_hash}"
            )
            file_history = FileHistoryHelper.get_file_history(
                workflow=workflow, cache_key=file_content_hash
            )

        return file_history

    def _create_file_hash(
        self, file_path: str, source_fs: UnstractFileSystem
    ) -> FileHash:
        """Create a FileHash object for the matched file."""
        file_name = os.path.basename(file_path)
        provider_file_uuid = source_fs.get_file_system_uuid(file_path)
        file_size = source_fs.get_file_size(file_path)
        fs_metadata = source_fs.get_file_metadata(file_path)
        connection_type = self.endpoint.connection_type
        return FileHash(
            file_path=file_path,
            source_connection_type=connection_type,
            file_name=file_name,
            file_size=file_size,
            provider_file_uuid=provider_file_uuid,
            fs_metadata=fs_metadata,
        )

    def list_files_from_source(
        self, file_hashes: dict[str, FileHash] = {}
    ) -> tuple[dict[str, FileHash], int]:
        """List files from source connector.

        Args:
            api_storage_dir (Optional[str], optional): API storage directory
        Returns:
            tuple[dict[str, FileHash], int]: A dictionary of FileHashes,
            along with the total count of matched files.
        """
        connection_type = self.endpoint.connection_type
        if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
            files, count = self.list_files_from_file_connector()
        elif connection_type == WorkflowEndpoint.ConnectionType.API:
            files, count = self.list_file_from_api_storage(file_hashes)
        else:
            raise InvalidSourceConnectionType()
        # TODO: move this to where file is listed at source.
        for index, file_hash in enumerate(files.values(), start=1):
            file_hash.file_number = index

        return files, count

    def get_file_content_hash(self, source_fs: UnstractFileSystem, file_path: str) -> str:
        """Generate a hash value from the file content.

        Args:
            source_fs (UnstractFileSystem): The file system object used for
                reading the file.
            file_path (str): The path of the file.

        Returns:
            str: The hash value of the file content.
        """
        file_content_hash = sha256()
        source = source_fs.get_fsspec_fs()
        with source.open(file_path, "rb") as remote_file:
            while chunk := remote_file.read(self.READ_CHUNK_SIZE):
                file_content_hash.update(chunk)
        return file_content_hash.hexdigest()

    def copy_file_to_infile_dir(self, source_file_path: str, infile_path: str) -> None:
        """Copy the source file to the infile directory.

        Args:
            source_file_path (str): The path of the source file.
            infile_path (str): The destination path in the infile directory.
        """
        shutil.copyfile(source_file_path, infile_path)
        logger.info(f"File copied from {source_file_path} to {infile_path}")

    def add_input_from_connector_to_volume(self, file_hash: FileHash) -> str:
        """Add input file to execution directory.

        Args:
            file_hash (FileHash): The file hash object.

        Returns:
            str: The hash value of the file content.

        Raises:
            FileHashNotFound: If the hash value of the file content is not found.
        """
        input_file_path = file_hash.file_path
        source_file_path = self.source_file
        infile_path = self.infile
        if not source_file_path or not infile_path:
            raise SourceFileOrInfilePathNotFound()
        connector: ConnectorInstance = self.endpoint.connector_instance
        connector_settings: dict[str, Any] = connector.connector_metadata
        source_fs = self.get_fsspec(
            settings=connector_settings, connector_id=connector.connector_id
        )

        workflow_file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        workflow_file_storage = workflow_file_system.get_file_storage()

        first_iteration = True
        input_log = ""
        file_hash = sha256()
        with source_fs.open(input_file_path, "rb") as remote_file:
            while chunk := remote_file.read(self.READ_CHUNK_SIZE):
                file_hash.update(chunk)
                if first_iteration:
                    input_log = (
                        chunk[:500].decode("utf-8", errors="replace") + "...(truncated)"
                    )
                    first_iteration = False
                # write the chunk in to execution directory
                workflow_file_storage.write(path=source_file_path, mode="ab", data=chunk)
                workflow_file_storage.write(path=infile_path, mode="ab", data=chunk)

        # publish input file content
        # TODO: Consider removing this since the input is not extracted text.
        # This function is typically relevant for extracted text content,
        # may not be necessary for PDFs, images, or other non-text formats.
        self.publish_input_file_content(input_file_path, input_log)
        hash_value_of_file_content = file_hash.hexdigest()
        logger.info(
            f"hash_value_of_file {source_file_path} is : {hash_value_of_file_content}"
        )

        logger.info(f"{input_file_path} is added to execution directory")
        return hash_value_of_file_content

    def add_input_from_api_storage_to_volume(self, input_file_path: str) -> str:
        """Add input file to execution directory from api storage."""
        source_file_path = self.source_file
        infile_path = self.infile
        if not source_file_path or not infile_path:
            raise SourceFileOrInfilePathNotFound()

        api_file_system = FileSystem(FileStorageType.API_EXECUTION)
        api_file_storage = api_file_system.get_file_storage()
        workflow_file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        workflow_file_storage = workflow_file_system.get_file_storage()
        file_content_hash = self._copy_file_to_destination(
            source_storage=api_file_storage,
            destination_storage=workflow_file_storage,
            source_path=input_file_path,
            destination_paths=[infile_path, source_file_path],
        )
        logger.info(f"File {input_file_path} added to execution directory")
        return file_content_hash

    # TODO: replace it with method from SDK Utils
    def _copy_file_to_destination(
        self,
        source_storage: FileStorage,
        destination_storage: FileStorage,
        source_path: str,
        destination_paths: list[str],
    ) -> str:
        """Copy a file from a source storage to one or more paths in a
        destination storage.

        This function reads the source file in chunks and writes each chunk to
        the specified destination paths. The function will continue until the
        entire source file is copied.

        Args:
            source_storage (FileStorage): The storage object from which
                the file is read.
            destination_storage (FileStorage): The storage object to which
                the file is written.
            source_path (str): The path of the file in the source storage.
            destination_paths (list[str]): A list of paths where the file will be
                copied in the destination storage.

        Returns:
            str: The SHA-256 hash of the file content.
        """
        seek_position = 0  # Start from the beginning
        file_content_hash = sha256()
        # Loop to read and write in chunks until the end of the file
        while chunk := source_storage.read(
            path=source_path,
            mode="rb",
            seek_position=seek_position,
            length=self.READ_CHUNK_SIZE,
        ):
            file_content_hash.update(chunk)
            # Write the chunk to each destination path
            for destination_file in destination_paths:
                destination_storage.write(
                    path=destination_file,
                    mode="ab",
                    data=chunk,
                )

            # Update the seek position
            seek_position += len(chunk)
        return file_content_hash.hexdigest()

    def add_file_to_volume(
        self,
        workflow_file_execution: WorkflowFileExecution,
        tags: list[str],
        file_hash: FileHash,
    ) -> str:
        """Add input file to execution directory.

        Args:
            workflow_file_execution: WorkflowFileExecution model
            tags (list[str]): Tag names associated with the workflow execution.
            file_hash: FileHash model

        Raises:
            InvalidSource: _description_

        Returns:
            str: file_name
        """
        connection_type = self.endpoint.connection_type
        input_file_path = file_hash.file_path
        if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
            file_content_hash = self.add_input_from_connector_to_volume(
                file_hash=file_hash
            )
        elif connection_type == WorkflowEndpoint.ConnectionType.API:
            file_content_hash = self.add_input_from_api_storage_to_volume(
                input_file_path=input_file_path
            )
        else:
            raise InvalidSourceConnectionType()

        self.add_metadata_to_volume(
            input_file_path=input_file_path,
            file_execution_id=workflow_file_execution.id,
            source_hash=file_content_hash,
            tags=tags,
        )
        return file_content_hash

    def handle_final_result(
        self,
        results: list[dict[str, Any]],
        file_name: str,
        result: str | None,
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
        cls,
        workflow_id: str,
        execution_id: str,
        file_objs: list[UploadedFile],
        use_file_history: bool = False,
    ) -> dict[str, FileHash]:
        """Add input file to api storage.

        Args:
            workflow_id (str): UUID of the worklfow
            execution_id (str): UUID of the execution
            file_objs (list[UploadedFile]): List of uploaded files
            use_file_history (bool): Use FileHistory table to return results on already
                processed files. Defaults to False
        Returns:
            dict[str, FileHash]: Dict containing file name and its corresponding hash
        """
        api_storage_dir = cls.get_api_storage_dir_path(
            workflow_id=workflow_id, execution_id=execution_id
        )
        workflow: Workflow = Workflow.objects.get(id=workflow_id)
        file_hashes: dict[str, FileHash] = {}
        for file in file_objs:
            file_name = file.name
            destination_path = os.path.join(api_storage_dir, file_name)

            file_system = FileSystem(FileStorageType.API_EXECUTION)
            file_storage = file_system.get_file_storage()
            file_hash = sha256()
            for chunk in file.chunks(chunk_size=cls.READ_CHUNK_SIZE):
                file_hash.update(chunk)
                file_storage.write(path=destination_path, mode="ab", data=chunk)
            file_hash = file_hash.hexdigest()
            connection_type = WorkflowEndpoint.ConnectionType.API

            file_history = None
            if use_file_history:
                file_history = FileHistoryHelper.get_file_history(
                    workflow=workflow, cache_key=file_hash
                )
            is_executed = True if file_history and file_history.is_completed() else False
            file_hash = FileHash(
                file_path=destination_path,
                source_connection_type=connection_type,
                file_name=file_name,
                file_hash=file_hash,
                is_executed=is_executed,
                file_size=file.size,
                mime_type=file.content_type,
            )
            file_hashes.update({file_name: file_hash})
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
        schema_path = os.path.join(os.path.dirname(__file__), "static", "src", "api.json")
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

    def get_config(self) -> SourceConfig:
        """Get serializable configuration for the source connector.

        Returns:
            SourceConfig: Configuration containing all necessary data to reconstruct the connector
        """
        source_config = SourceConfig(
            workflow_id=self.workflow.id,
            execution_id=self.execution_id,
            organization_id=self.organization_id,
            use_file_history=self.use_file_history,
        )
        return source_config

    @classmethod
    def from_config(
        cls, workflow_log: WorkflowLog, config: SourceConfig
    ) -> "SourceConnector":
        """Create a SourceConnector instance from configuration.

        Args:
            workflow_log (WorkflowLog): Workflow log instance
            config (SourceConfig): Configuration containing all necessary data to reconstruct the connector

        Returns:
            SourceConnector: New instance
        """
        # Reconstruct workflow
        workflow = Workflow.objects.get(id=config.workflow_id)

        # Create source connector instance
        source = cls(
            workflow=workflow,
            execution_id=config.execution_id,
            workflow_log=workflow_log,
            use_file_history=config.use_file_history,
            organization_id=config.organization_id,
            file_execution_id=config.file_execution_id,
        )

        return source
