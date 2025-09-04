import fnmatch
import logging
import os
import shutil
import uuid
from hashlib import sha256
from io import BytesIO
from itertools import islice
from typing import Any

import fsspec
import magic
from connector_processor.constants import ConnectorKeys
from connector_v2.models import ConnectorInstance
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q
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
from workflow_manager.endpoint_v2.enums import AllowedFileTypes
from workflow_manager.endpoint_v2.exceptions import (
    InvalidInputDirectory,
    InvalidSourceConnectionType,
    MissingSourceConnectionType,
    OrganizationIdNotFound,
    SourceConnectorNotConfigured,
    SourceFileOrInfilePathNotFound,
    UnsupportedMimeTypeError,
)
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.utils.workflow_log import WorkflowLog
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.filesystem import FileStorageType, FileSystem
from unstract.sdk.file_storage import FileStorage
from unstract.workflow_execution.enums import LogStage, LogState

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
        valid_directories = []
        for input_directory in folders_to_process:
            # TODO: Move to connector class for better error handling
            try:
                input_directory = source_fs.get_connector_root_dir(
                    input_dir=input_directory, root_path=root_dir_path
                )
                if not source_fs_fsspec.isdir(input_directory):
                    raise InvalidInputDirectory(dir=input_directory)
                valid_directories.append(input_directory)
            except Exception as e:
                msg = f"Error while validating path '{input_directory}'. {str(e)}"
                self.publish_user_sys_log(msg)
                if isinstance(e, InvalidInputDirectory):
                    raise
                raise InvalidInputDirectory(detail=msg)

        total_files_to_process = 0
        total_matched_files = {}
        unique_file_paths: set[str] = set()

        for input_directory in valid_directories:
            logger.debug(f"Listing files from:  {input_directory}")
            matched_files, count = self._get_matched_files(
                source_fs,
                input_directory,
                patterns,
                recursive,
                limit,
                unique_file_paths,
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
        unique_file_paths: set[str],
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
        for root, dirs, _ in fs_fsspec.walk(input_directory, maxdepth=max_depth):
            try:
                fs_metadata_list: list[dict[str, Any]] = fs_fsspec.listdir(
                    root
                )  # Single call for file system metadata
            except Exception as e:
                logger.warning(f"Failed to list directory from path: {root}, error: {e}")
                continue

            count = self._process_file_fs_directory(
                fs_metadata_list=fs_metadata_list,
                count=count,
                limit=limit,
                unique_file_paths=unique_file_paths,
                matched_files=matched_files,
                patterns=patterns,
                source_fs=source_fs,
                dirs=dirs,
            )
        return matched_files, count

    def _process_file_fs_directory(
        self,
        fs_metadata_list: list[dict[str, Any]],
        count: int,
        limit: int,
        unique_file_paths: set[str],
        matched_files: dict[str, FileHash],
        patterns: list[str],
        source_fs: UnstractFileSystem,
        dirs: list[str],
    ) -> int:
        for fs_metadata in fs_metadata_list:
            if count >= limit:
                msg = f"Maximum limit of '{limit}' files to process reached"
                self.workflow_log.publish_log(msg)
                logger.info(msg)
                break

            file_path: str | None = fs_metadata.get("name")
            file_size = fs_metadata.get("size", 0)

            if not file_path or self._is_directory(
                source_fs, file_path, fs_metadata, dirs
            ):
                continue

            file_hash = self._create_file_hash(
                file_path=file_path,
                source_fs=source_fs,
                file_size=file_size,
                fs_metadata=fs_metadata,
            )
            if self._should_skip_file(file_hash, patterns):
                continue

            # Skip duplicate files
            if self._is_duplicate(file_hash, unique_file_paths):
                msg = f"Skipping execution of duplicate file '{file_path}'"
                self.workflow_log.publish_log(msg)
                logger.info(msg)
                continue
            self._update_unique_file_paths(file_hash, unique_file_paths)

            matched_files[file_path] = file_hash
            count += 1
        return count

    def _is_file_being_processed(self, file_hash: FileHash) -> bool:
        """Check if file is currently being processed or should be skipped
        Uses direct database queries instead of FileExecutionStatusTracker

        Args:
            file_hash (FileHash): The file hash to check

        Returns:
            bool: True if file should be skipped (being processed or already completed), False otherwise
        """
        active_executions = self._get_active_workflow_executions()
        logger.info(
            f"Found {len(active_executions)} active executions for workflow {self.workflow.id}"
        )

        for execution in active_executions:
            if self._has_blocking_file_execution(execution, file_hash):
                return True

        return False

    def _get_active_workflow_executions(self):
        """Get active executions for this workflow with organization filtering for security."""
        organization = UserContext.get_organization()
        return WorkflowExecution.objects.filter(
            workflow=self.workflow,
            workflow__organization_id=organization.id,  # Security: Organization isolation
            status__in=[ExecutionStatus.EXECUTING, ExecutionStatus.PENDING],
        )

    def _has_blocking_file_execution(self, execution, file_hash: FileHash) -> bool:
        """Check if there's a blocking file execution that prevents processing."""
        try:
            # Try to find blocking file execution using file_hash
            file_exec = self._find_blocking_file_execution_by_hash(execution, file_hash)
            if file_exec:
                self._log_duplicate_file_execution_skip(file_hash, file_exec, execution)
                return True

            # Try to find blocking file execution using provider_file_uuid
            file_exec = self._find_blocking_file_execution_by_provider_uuid(
                execution, file_hash
            )
            if file_exec:
                self._log_duplicate_file_execution_skip(file_hash, file_exec, execution)
                return True

        except Exception as e:
            logger.warning(
                f"Error checking file execution status for {file_hash.file_name}: {e}\n"
                "Allowing its execution to continue anyway"
            )

        return False

    def _find_blocking_file_execution_by_hash(self, execution, file_hash: FileHash):
        """Find blocking file execution by file hash if it exists."""
        if not file_hash.file_hash:
            return None

        try:
            return WorkflowFileExecution.objects.get(
                workflow_execution=execution,
                file_hash=file_hash.file_hash,
                file_path=file_hash.file_path,
                status__in=ExecutionStatus.get_skip_processing_statuses(),
            )
        except WorkflowFileExecution.DoesNotExist:
            return None

    def _find_blocking_file_execution_by_provider_uuid(
        self, execution, file_hash: FileHash
    ):
        """Find blocking file execution by provider UUID if it exists."""
        if not file_hash.provider_file_uuid:
            return None

        try:
            return WorkflowFileExecution.objects.get(
                workflow_execution=execution,
                provider_file_uuid=file_hash.provider_file_uuid,
                file_path=file_hash.file_path,
                status__in=ExecutionStatus.get_skip_processing_statuses(),
            )
        except WorkflowFileExecution.DoesNotExist:
            return None

    def _log_duplicate_file_execution_skip(
        self, file_hash: FileHash, file_exec, execution
    ):
        """Log message when skipping file due to duplicate/blocking execution."""
        message = (
            f"Skipping file '{file_hash.file_name}' - status: {file_exec.status} "
            f"in execution {execution.id}, file execution id: {file_exec.id}"
        )
        self.workflow_log.publish_log(message)
        logger.info(message)

    def _should_skip_file(
        self,
        file_hash: FileHash,
        patterns: list[str],
    ) -> bool:
        """Check if the given file should be skipped.

        Args:
            file_hash (FileHash): The hash of the file.
            patterns (list[str]): The patterns to match against file names.

        Returns:
            bool: True if the file should be skipped, False otherwise.
        """
        file_name = os.path.basename(file_hash.file_path)

        # Existing pattern check
        if not self._should_process_file(file_name, patterns):
            return True

        # Existing file history check
        if not self._is_new_file(file_hash=file_hash, workflow=self.endpoint.workflow):
            return True

        # NEW: Check if file is being processed
        if self._is_file_being_processed(file_hash):
            return True

        return False

    def _is_duplicate(self, file_hash: FileHash, unique_file_paths: set[str]) -> bool:
        return (
            file_hash.file_path in unique_file_paths
            or file_hash.file_name in unique_file_paths
        )

    def _update_unique_file_paths(
        self, file_hash: FileHash, unique_file_paths: set[str]
    ) -> None:
        if file_hash.file_path:
            unique_file_paths.add(file_hash.file_path)
        elif file_hash.file_name:
            unique_file_paths.add(file_hash.file_name)

    def _is_directory(
        self,
        source_fs: UnstractFileSystem,
        file_path: str,
        metadata: dict[str, Any],
        dirs: list[str],
    ) -> bool:
        """Check if the given path is a directory.

        Args:
            source_fs (UnstractFileSystem): The file system object used for
                reading the file.
            file_path (str): The path of the file.
            metadata (dict[str, Any]): The metadata of the file.
            dirs (list[str]): The list of directories.

        Returns:
            bool: True if the file is a directory, False otherwise.
        """
        try:
            # Check if the path is a directory using metadata first.
            # Some connectors incorrectly label directories as files, so if metadata is inconclusive or fails,
            # fall back to other checks: directory listing, path suffix ("/"), or zero file size.
            if source_fs.is_dir_by_metadata(metadata):
                logger.info(
                    f"[Directory Check] '{file_path}' identified as a directory via metadata."
                )
                return True
        except NotImplementedError:
            logger.debug(
                f"[Directory Check] Metadata-based check not implemented for '{file_path}'."
            )
        except Exception as e:
            logger.warning(
                f"[Directory Check] Error while checking metadata for '{file_path}': {e}"
            )

        file_name = os.path.basename(file_path)

        # Fallback 1: Check if the file is explicitly listed in directory entries
        if file_name in dirs:
            logger.info(
                f"[Directory Check] '{file_path}' identified as a directory via checking list of directories."
            )
            return True

        # Fallback 2: Check if the path ends with a slash
        if file_path.endswith("/"):
            logger.info(
                f"[Directory Check] '{file_path}' identified as a directory based on path suffix '/'."
            )
            return True

        # Fallback 3: Check if the file has size zero
        if source_fs.get_file_size(metadata=metadata) == 0:
            logger.info(
                f"[Directory Check] '{file_path}' identified as a directory based on file size = 0."
            )
            return True

        return False

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
        if not FilePattern.is_supported(file_name):
            message = f"Skipping '{file_name}' as it has an unsupported file format"
            logger.debug(message)
            self.workflow_log.publish_log(message)
            return False

        return True

    def _is_new_file(
        self,
        file_hash: FileHash,
        workflow: Workflow,
    ) -> bool:
        """Check if the file is new or already processed."""
        # Always treat the file as new if history usage is not enforced
        if not self.use_file_history:
            return True

        # Always treat the file as new if neither identifier is available
        if not file_hash.provider_file_uuid and not file_hash.file_hash:
            return True

        current_file_path = file_hash.file_path
        file_history = self._get_file_history(file_hash=file_hash, workflow=workflow)

        # No history or incomplete history means the file is new
        if not file_history or not file_history.is_completed():
            return True

        # Note: To enforce content-only deduplication (ignoring file path), introduce a
        # `use_content_deduplication_only` flag. If enabled, apply the check here and return False accordingly.

        # Compare file paths
        if file_history.file_path and file_history.file_path != current_file_path:
            return True

        # Default: file has been processed with the same path
        self._log_file_skipped(current_file_path)
        return False

    def _log_file_skipped(self, file_path: str):
        """Log a message indicating that a file has been skipped.

        Args:
            file_path (str): The path of the file.
        """
        msg = f"Skipping file '{file_path}' as it has already been processed."
        self.workflow_log.publish_log(
            msg + " Clear the file markers to process it again."
        )
        logger.info(msg)

    def _get_file_history(
        self,
        file_hash: FileHash,
        workflow: Workflow,
    ) -> FileHistory | None:
        """Retrieve file history using provider UUID or legacy cache key."""
        provider_file_uuid = file_hash.provider_file_uuid
        # Note: For content-only deduplication, use the `use_content_deduplication_only` flag to fetch file history
        # without including file path as a filter.

        if provider_file_uuid:
            logger.info(f"Checking file history for provider UUID: {provider_file_uuid}")
            return FileHistoryHelper.get_file_history(
                workflow=workflow,
                provider_file_uuid=provider_file_uuid,
                file_path=file_hash.file_path,
                workflow_log=self.workflow_log,
            )
        return None

    def _get_file_execution_by_file_hash(
        self,
        file_hash: FileHash,
        workflow: Workflow,
    ) -> WorkflowFileExecution | None:
        """Retrieve file execution by file hash."""
        # Build base query conditions
        base_conditions = Q(workflow_execution__workflow=workflow)
        content_conditions = Q()
        if file_hash.provider_file_uuid:
            content_conditions |= Q(provider_file_uuid=file_hash.provider_file_uuid)
        if file_hash.file_hash:
            content_conditions |= Q(file_hash=file_hash.file_hash)

        # Filter file executions based on conditions
        conditions = base_conditions & content_conditions
        file_execution = WorkflowFileExecution.objects.filter(conditions).first()
        if file_execution:
            return file_execution
        return None

    def _create_file_hash(
        self,
        file_path: str,
        source_fs: UnstractFileSystem,
        file_size: int,
        fs_metadata: dict[str, Any],
    ) -> FileHash:
        """Create a FileHash object for the matched file."""
        file_name = os.path.basename(file_path)
        provider_file_uuid = source_fs.get_file_system_uuid(
            file_path=file_path, metadata=fs_metadata
        )
        serialized_metadata = source_fs.serialize_metadata_value(value=fs_metadata)
        connection_type = self.endpoint.connection_type
        return FileHash(
            file_path=file_path,
            source_connection_type=connection_type,
            file_name=file_name,
            file_size=file_size,
            provider_file_uuid=provider_file_uuid,
            fs_metadata=serialized_metadata,
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
        logger.info(
            f"Adding input file from source connector to execution directory: {file_hash.file_name}"
        )
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
        file_content_hash = sha256()
        with source_fs.open(input_file_path, "rb") as remote_file:
            while chunk := remote_file.read(self.READ_CHUNK_SIZE):
                file_content_hash.update(chunk)
                if first_iteration:
                    # Detect MIME type using first chunk
                    mime_type = magic.from_buffer(chunk, mime=True)
                    logger.info(
                        f"Detected MIME type: {mime_type} for file {input_file_path}"
                    )
                    if not AllowedFileTypes.is_allowed(mime_type):
                        raise UnsupportedMimeTypeError(
                            f"Unsupported MIME type '{mime_type}' for file '{input_file_path}'"
                        )
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
        hash_value_of_file_content = file_content_hash.hexdigest()
        file_hash.mime_type = mime_type
        logger.info(
            f"hash_value_of_file {source_file_path} is : {hash_value_of_file_content}"
        )

        logger.info(f"{input_file_path} is added to execution directory")
        return hash_value_of_file_content

    def add_input_from_api_storage_to_volume(self, input_file_path: str) -> str:
        """Add input file to execution directory from api storage."""
        logger.info(
            f"Adding input file from api storage to execution directory: {input_file_path}"
        )
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
        llm_profile_id: str | None = None,
    ) -> str:
        """Add input file to execution directory.

        Args:
            workflow_file_execution: WorkflowFileExecution model
            tags (list[str]): Tag names associated with the workflow execution.
            file_hash: FileHash model
            llm_profile_id (str, optional): LLM profile ID for overriding tool settings.

        Raises:
            InvalidSource: _description_

        Returns:
            str: file_name
        """
        logger.info(f"Adding input file to execution directory: {file_hash.file_name}")
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
            # Filehash created from Django requests files might be different
            # from file_content_hash created from file content here.
            # So use file_content_hash only when file_hash is not available
            file_content_hash = (
                file_hash.file_hash if file_hash.file_hash else file_content_hash
            )
        else:
            raise InvalidSourceConnectionType()

        self.add_metadata_to_volume(
            input_file_path=input_file_path,
            file_execution_id=workflow_file_execution.id,
            source_hash=file_content_hash,
            tags=tags,
            llm_profile_id=llm_profile_id,
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
        pipeline_id: str,
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
        org_schema = UserContext.get_organization_identifier()
        workflow_log = WorkflowLog(
            execution_id=execution_id,
            log_stage=LogStage.SOURCE,
            pipeline_id=pipeline_id,
            organization_id=org_schema,
        )
        workflow_log.publish_log(
            "Staging files in API storage for validation and processing."
        )
        api_storage_dir = cls.get_api_storage_dir_path(
            workflow_id=workflow_id, execution_id=execution_id
        )
        workflow: Workflow = Workflow.objects.get(id=workflow_id)
        file_hashes: dict[str, FileHash] = {}
        unique_file_hashes: set[str] = set()
        connection_type = WorkflowEndpoint.ConnectionType.API
        for file in file_objs:
            file_name = file.name
            destination_path = os.path.join(api_storage_dir, file_name)

            mime_type = file.content_type
            logger.info(f"Detected MIME type: {mime_type} for file {file_name}")
            if not mime_type:
                logger.info(
                    f"MIME type not found for file {file_name}, using default MIME type: {AllowedFileTypes.OCTET_STREAM.value}"
                )
                mime_type = AllowedFileTypes.OCTET_STREAM.value

            if not AllowedFileTypes.is_allowed(mime_type):
                log_message = f"Skipping file '{file_name}' to stage due to unsupported MIME type '{mime_type}'"
                workflow_log.log_info(logger=logger, message=log_message)
                # Generate a clearly marked temporary hash to avoid reading the file content
                # Helps to prevent duplicate entries in file executions
                fake_hash = f"temp-hash-{uuid.uuid4().hex}"
                file_hash = FileHash(
                    file_path=destination_path,
                    source_connection_type=connection_type,
                    file_name=file_name,
                    file_hash=fake_hash,
                    is_executed=True,
                    file_size=file.size,
                    mime_type=mime_type,
                )
                file_hashes.update({file_name: file_hash})
                continue

            file_system = FileSystem(FileStorageType.API_EXECUTION)
            file_storage = file_system.get_file_storage()
            file_hash = sha256()
            for chunk in file.chunks(chunk_size=cls.READ_CHUNK_SIZE):
                file_hash.update(chunk)
                file_storage.write(path=destination_path, mode="ab", data=chunk)
            file_hash = file_hash.hexdigest()

            # Skip duplicate files
            if file_hash in unique_file_hashes:
                log_message = f"Skipping file '{file_name}' — duplicate detected within the current request. Already staged for processing."
                workflow_log.log_info(logger=logger, message=log_message)
                continue
            unique_file_hashes.add(file_hash)

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
                mime_type=mime_type,
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
