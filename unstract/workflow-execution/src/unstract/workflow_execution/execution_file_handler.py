import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import fsspec
from unstract.workflow_execution.constants import (
    FeatureFlag,
    MetaDataKey,
    ToolMetadataKey,
    ToolOutputType,
    ToolRuntimeVariable,
    WorkflowFileType,
)
from unstract.workflow_execution.exceptions import ToolMetadataNotFound
from unstract.workflow_execution.tools_utils import ToolsUtils

from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
    from unstract.filesystem import FileStorageType, FileSystem

logger = logging.getLogger(__name__)


class ExecutionFileHandler:
    def __init__(
        self, workflow_id: str, execution_id: str, organization_id: str
    ) -> None:
        self.organization_id = organization_id
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
            self.execution_dir = self.get_execution_dir(
                workflow_id, execution_id, organization_id
            )
        else:
            self.execution_dir = self.create_execution_dir_path(
                workflow_id, execution_id, organization_id
            )
        self.source_file = os.path.join(self.execution_dir, WorkflowFileType.SOURCE)
        self.infile = os.path.join(self.execution_dir, WorkflowFileType.INFILE)
        self.metadata_file = os.path.join(
            self.execution_dir, WorkflowFileType.METADATA_JSON
        )

    def get_workflow_metadata(self) -> dict[str, Any]:
        """Get metadata for the workflow.

        Returns:
            dict[str, Any]: Workflow metadata.
        """
        if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()
            metadata_content = file_storage.read(path=self.metadata_file, mode="r")
            metadata = json.loads(metadata_content)
        else:
            with open(self.metadata_file) as file:
                metadata: dict[str, Any] = json.load(file)
        return metadata

    def get_list_of_tool_metadata(
        self, metadata: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get the list of tool metadata from the workflow metadata.

        Args:
            metadata (dict[str, Any]): The workflow metadata.

        Returns:
            list[dict[str, Any]]: The list of tool metadata.
        """
        tool_metadata: list[dict[str, Any]] = metadata.get(
            MetaDataKey.TOOL_METADATA, []
        )
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

    def add_metadata_to_volume(self, input_file_path: str, source_hash: str) -> None:
        """Creating metadata for workflow. This method is responsible for
        creating metadata for the workflow. It takes the input file path and
        the source hash as parameters. The metadata is stored in a JSON file in
        the execution directory.

        Parameters:
            input_file_path (str): The path of the input file.
            source_hash (str): The hash value of the source/input file.

        Returns:
            None

        Raises:
            None
        """
        metadata_path = os.path.join(self.execution_dir, WorkflowFileType.METADATA_JSON)
        filename = os.path.basename(input_file_path)
        content = {
            MetaDataKey.SOURCE_NAME: filename,
            MetaDataKey.SOURCE_HASH: source_hash,
            MetaDataKey.ORGANIZATION_ID: str(self.organization_id),
            MetaDataKey.WORKFLOW_ID: str(self.workflow_id),
            MetaDataKey.EXECUTION_ID: str(self.execution_id),
        }
        if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()
            file_storage.json_dump(path=metadata_path, data=content)
        else:
            with fsspec.open(f"file://{metadata_path}", "w") as local_file:
                json.dump(content, local_file)

        logger.info(
            f"metadata for {input_file_path} is " "added in to execution directory"
        )

    @classmethod
    def create_execution_dir_path(
        cls,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        data_volume: Optional[str] = None,
    ) -> str:
        """Create the directory path for storing execution-related files.

        Parameters:
        - workflow_id (str): Identifier for the workflow.
        - execution_id (str): Identifier for the execution.
        - organization_id (Optional[str]):
            Identifier for the organization (default: None).

        Returns:
        str: The directory path for the execution.
        """
        workflow_data_dir = os.getenv("WORKFLOW_DATA_DIR")
        data_volume = data_volume if data_volume else workflow_data_dir
        if not data_volume:
            raise ValueError("Missed data_volume")
        execution_dir = Path(
            data_volume, organization_id, str(workflow_id), str(execution_id)
        )
        execution_dir.mkdir(parents=True, exist_ok=True)
        return str(execution_dir)

    @classmethod
    def get_execution_dir(
        cls, workflow_id: str, execution_id: str, organization_id: str
    ) -> str:
        """Create the directory path for storing execution-related files.

        Parameters:
        - workflow_id (str): Identifier for the workflow.
        - execution_id (str): Identifier for the execution.
        - organization_id (Optional[str]):
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
        - organization_id (Optional[str]):
            Identifier for the organization (default: None).

        Returns:
        str: The directory path for the execution.
        """
        path_prefix = ToolsUtils.get_env(ToolRuntimeVariable.API_EXECUTION_DIR_PREFIX)
        execution_dir = (
            Path(path_prefix) / organization_id / str(workflow_id) / str(execution_id)
        )
        return str(execution_dir)
