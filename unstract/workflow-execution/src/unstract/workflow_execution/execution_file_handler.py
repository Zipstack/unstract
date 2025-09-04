import json
import logging
import os
from pathlib import Path
from typing import Any

from unstract.filesystem import FileStorageType, FileSystem
from unstract.workflow_execution.constants import (
    MetaDataKey,
    ToolMetadataKey,
    ToolOutputType,
    ToolRuntimeVariable,
    WorkflowFileType,
)
from unstract.workflow_execution.exceptions import (
    ExecutionDirectoryNotFound,
    FileExecutionNotFound,
    FileMetadataJsonNotFound,
    ToolMetadataNotFound,
)
from unstract.workflow_execution.tools_utils import ToolsUtils

logger = logging.getLogger(__name__)


class ExecutionFileHandler:
    def __init__(
        self,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        file_execution_id: str | None = None,
    ) -> None:
        self.organization_id = organization_id
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.file_execution_id = file_execution_id
        self.execution_dir = self.get_execution_dir(
            workflow_id, execution_id, organization_id
        )
        self.file_execution_dir = self._get_file_execution_dir()
        self.source_file = self._get_source_file_path()
        self.infile = self._get_infile_path()
        self.metadata_file = self._get_metadata_file_path()

    def get_workflow_metadata(self) -> dict[str, Any]:
        """Get metadata for the workflow.

        Returns:
            dict[str, Any]: Workflow metadata.
        """
        if not self.metadata_file:
            raise FileMetadataJsonNotFound()
        file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        file_storage = file_system.get_file_storage()
        metadata_content = file_storage.read(path=self.metadata_file, mode="r")
        metadata = json.loads(metadata_content)
        return metadata

    def get_list_of_tool_metadata(self, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        """Get the list of tool metadata from the workflow metadata.

        Args:
            metadata (dict[str, Any]): The workflow metadata.

        Returns:
            list[dict[str, Any]]: The list of tool metadata.
        """
        tool_metadata: list[dict[str, Any]] = metadata.get(MetaDataKey.TOOL_METADATA, [])
        return tool_metadata

    def get_output_type(self, metadata: dict[str, Any]) -> str:
        """Get the output type from the metadata.

        This method retrieves the output type from the metadata dictionary.

        Args:
            metadata (dict[str, Any]): The metadata dictionary.

        Returns:
            str: The output type.

        Raises:
            ToolMetadataNotFound: If the 'tool_metadata' key is empty.
        """
        metadata_of_last_tool = self.get_last_tool_metadata(metadata)
        output_type: str = metadata_of_last_tool.get(
            ToolMetadataKey.OUTPUT_TYPE, ToolOutputType.TXT
        )
        return output_type

    def get_last_tool_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        tool_metadata = self.get_list_of_tool_metadata(metadata)
        if not tool_metadata:
            raise ToolMetadataNotFound()
        return tool_metadata[-1]

    def add_metadata_to_volume(
        self,
        input_file_path: str,
        file_execution_id: str,
        source_hash: str,
        tags: list[str],
        llm_profile_id: str | None = None,
    ) -> None:
        """Creating metadata for workflow. This method is responsible for
        creating metadata for the workflow. It takes the input file path and
        the source hash as parameters. The metadata is stored in a JSON file in
        the execution directory.

        Parameters:
            input_file_path (str): The path of the input file.
            file_execution_id (str): Unique execution id for the file.
            source_hash (str): The hash value of the source/input file.
            tags (list[str]): Tag names associated with the workflow execution.
            llm_profile_id (str, optional): LLM profile ID for overriding tool settings.

        Returns:
            None

        Raises:
            None
        """
        if not self.file_execution_dir:
            raise FileExecutionNotFound()
        metadata_path = self.metadata_file
        if not metadata_path:
            raise FileMetadataJsonNotFound()
        filename = os.path.basename(input_file_path)
        content = {
            MetaDataKey.SOURCE_NAME: filename,
            MetaDataKey.SOURCE_HASH: source_hash,
            MetaDataKey.ORGANIZATION_ID: str(self.organization_id),
            MetaDataKey.WORKFLOW_ID: str(self.workflow_id),
            MetaDataKey.EXECUTION_ID: str(self.execution_id),
            MetaDataKey.FILE_EXECUTION_ID: str(file_execution_id),
            MetaDataKey.TAGS: tags,
        }

        # Add llm_profile_id to metadata if provided
        if llm_profile_id:
            content[MetaDataKey.LLM_PROFILE_ID] = llm_profile_id

        file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        file_storage = file_system.get_file_storage()
        file_storage.json_dump(path=metadata_path, data=content)

        logger.info(
            f"metadata for {input_file_path} is " "added in to execution directory"
        )

    def _get_file_execution_dir(self) -> str | None:
        """Get the directory path for a specific file execution.

        Returns:
            str: (Optional) The directory path for the file execution.
        """
        if not self.execution_dir:
            raise ExecutionDirectoryNotFound()
        if not self.file_execution_id:
            return None
        return os.path.join(self.execution_dir, self.file_execution_id)

    @classmethod
    def get_execution_dir(
        cls, workflow_id: str, execution_id: str, organization_id: str
    ) -> str:
        """Create the directory path for storing execution-related files.

        Parameters:
        - workflow_id (str): Identifier for the workflow.
        - execution_id (str): Identifier for the execution.
        - organization_id (str | None):
            Identifier for the organization (default: None).

        Returns:
        str: The directory path for the execution.
        """
        path_prefix = ToolsUtils.get_env(
            ToolRuntimeVariable.WORKFLOW_EXECUTION_DIR_PREFIX
        )
        execution_dir = (
            Path(path_prefix) / organization_id / str(workflow_id) / str(execution_id)
        )

        return str(execution_dir)

    @classmethod
    def get_api_execution_dir(
        cls, workflow_id: str, execution_id: str, organization_id: str
    ) -> str:
        """Create the directory path for storing execution-related files.

        Parameters:
        - workflow_id (str): Identifier for the workflow.
        - execution_id (str): Identifier for the execution.
        - organization_id (str | None):
            Identifier for the organization (default: None).

        Returns:
        str: The directory path for the execution.
        """
        path_prefix = ToolsUtils.get_env(ToolRuntimeVariable.API_EXECUTION_DIR_PREFIX)
        execution_dir = (
            Path(path_prefix) / organization_id / str(workflow_id) / str(execution_id)
        )
        return str(execution_dir)

    def _get_source_file_path(self) -> str | None:
        """Returns:
        str: (Optional) The path to the source file.
        """
        if not self.file_execution_dir:
            return None
        else:
            return os.path.join(self.file_execution_dir, WorkflowFileType.SOURCE)

    def _get_infile_path(self) -> str | None:
        """Returns:
        str: (Optional) The path to the infile.
        """
        if not self.file_execution_dir:
            return None
        return os.path.join(self.file_execution_dir, WorkflowFileType.INFILE)

    def _get_metadata_file_path(self) -> str | None:
        """Get the path to the metadata file.

        Args:
            None
        Returns: str: (Optional) The path to the metadata file.
        """
        if not self.file_execution_dir:
            return None
        return os.path.join(self.file_execution_dir, WorkflowFileType.METADATA_JSON)

    def delete_file_execution_directory(self) -> None:
        """Delete the file execution directory and all its contents.

        This method cleans up temporary files created during workflow execution.
        It's safe to call even if the directory doesn't exist.
        """
        if not self.file_execution_dir:
            logger.debug("No file execution directory to delete")
            return

        try:
            file_path = Path(self.file_execution_dir)
            if file_path.exists() and file_path.is_dir():
                import shutil

                shutil.rmtree(file_path)
                logger.debug(
                    f"Deleted file execution directory: {self.file_execution_dir}"
                )
            else:
                logger.debug(
                    f"File execution directory does not exist: {self.file_execution_dir}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to delete file execution directory {self.file_execution_dir}: {str(e)}"
            )
            # Don't raise exception as cleanup failure shouldn't stop execution
