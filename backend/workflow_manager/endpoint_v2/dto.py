import json
from dataclasses import dataclass
from typing import Any

from workflow_manager.endpoint_v2.constants import (
    ApiDeploymentResultStatus,
)


@dataclass
class FileHash:
    file_path: str
    file_name: str
    source_connection_type: str
    file_hash: str | None = None
    file_size: int | None = None
    provider_file_uuid: str | None = None
    mime_type: str | None = None
    fs_metadata: dict[str, Any] | None = None
    file_destination: tuple[str, str] | None = (
        None  # To which destination this file wants to go for MRQ percentage
    )
    is_executed: bool = False
    file_number: int | None = None
    is_manualreview_required: bool = False  # Added for manual review support

    def to_json(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "file_name": self.file_name,
            "source_connection_type": self.source_connection_type,
            "file_destination": self.file_destination,
            "is_executed": self.is_executed,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "provider_file_uuid": self.provider_file_uuid,
            "fs_metadata": self.fs_metadata,
            "file_number": self.file_number,
            "is_manualreview_required": self.is_manualreview_required,
        }

    def to_serialized_json(self) -> str:
        """Serialize the FileHash instance to a JSON string."""
        return json.dumps(self.to_json())

    @staticmethod
    def from_json(json_str_or_dict: Any) -> "FileHash":
        """Deserialize a JSON string or dictionary to a FileHash instance."""
        if isinstance(json_str_or_dict, dict):
            # If already a dictionary, assume it's in the right format
            data = json_str_or_dict
        else:
            # Otherwise, assume it's a JSON string
            data = json.loads(json_str_or_dict)
        return FileHash(**data)


@dataclass
class SourceConfig:
    workflow_id: str
    execution_id: str
    organization_id: str
    use_file_history: bool
    file_execution_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize the SourceConfig instance to a JSON string."""
        file_execution_id = (
            str(self.file_execution_id) if self.file_execution_id else None
        )
        return {
            "workflow_id": str(self.workflow_id),
            "execution_id": str(self.execution_id),
            "organization_id": str(self.organization_id),
            "use_file_history": self.use_file_history,
            "file_execution_id": file_execution_id,
        }

    @staticmethod
    def from_json(json_str_or_dict: Any) -> "SourceConfig":
        """Deserialize a JSON string or dictionary to a SourceConfig instance."""
        if isinstance(json_str_or_dict, dict):
            data = json_str_or_dict
        else:
            data = json.loads(json_str_or_dict)
        return SourceConfig(**data)


@dataclass
class DestinationConfig:
    workflow_id: str
    execution_id: str
    use_file_history: bool
    file_execution_id: str | None = None
    hitl_queue_name: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize the DestinationConfig instance to a JSON string."""
        file_execution_id = (
            str(self.file_execution_id) if self.file_execution_id else None
        )
        return {
            "workflow_id": str(self.workflow_id),
            "execution_id": str(self.execution_id),
            "use_file_history": self.use_file_history,
            "file_execution_id": file_execution_id,
            "hitl_queue_name": self.hitl_queue_name,
        }

    @staticmethod
    def from_json(json_str_or_dict: Any) -> "DestinationConfig":
        """Deserialize a JSON string or dictionary to a DestinationConfig instance."""
        if isinstance(json_str_or_dict, dict):
            data = json_str_or_dict
        else:
            data = json.loads(json_str_or_dict)

        return DestinationConfig(**data)


@dataclass
class FileExecutionResult:
    file: str
    file_execution_id: str | None = None
    status: str | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.error:
            self.status = ApiDeploymentResultStatus.FAILED
        else:
            self.status = ApiDeploymentResultStatus.SUCCESS

    def to_json(self) -> dict[str, Any]:
        """Serialize the FileExecutionResult instance to a JSON string."""
        return {
            "file": self.file,
            "file_execution_id": self.file_execution_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_json(json_str_or_dict: Any) -> "FileExecutionResult":
        """Deserialize a JSON string or dictionary to a FileExecutionResult instance."""
        if isinstance(json_str_or_dict, dict):
            data = json_str_or_dict
        else:
            data = json.loads(json_str_or_dict)
        return FileExecutionResult(**data)
