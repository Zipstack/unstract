import json
import logging
import os
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import redis

from unstract.core.exceptions import (
    FileExecutionStageException,
    FileExecutionTrackerNotFound,
    FileExecutionTrackerValueException,
)

logger = logging.getLogger(__name__)


class FileExecutionStage(Enum):
    INITIALIZATION = "INITIALIZATION"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    FINALIZATION = "FINALIZATION"
    COMPLETED = "COMPLETED"

    @property
    def order(self) -> int:
        return FILE_EXECUTION_STAGE_ORDER[self]

    def can_move_to(self, other: "FileExecutionStage") -> bool:
        """Check if the stage can move to the other stage."""
        return self.order < other.order

    def is_before(self, other: "FileExecutionStage") -> bool:
        """Check if the stage is before the other stage."""
        return self.order < other.order

    def is_after(self, other: "FileExecutionStage") -> bool:
        """Check if the stage is after the other stage."""
        return self.order > other.order


FILE_EXECUTION_STAGE_ORDER = {
    FileExecutionStage.INITIALIZATION: 0,
    FileExecutionStage.TOOL_EXECUTION: 1,
    FileExecutionStage.FINALIZATION: 2,
    FileExecutionStage.COMPLETED: 3,
}


class FileExecutionStageStatus(Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class FileExecutionField:
    EXECUTION_ID = "execution_id"
    FILE_EXECUTION_ID = "file_execution_id"
    ORGANIZATION_ID = "organization_id"
    STAGE = "stage"
    STATUS = "status"
    ERROR = "error"
    STAGE_STATUS = "stage_status"
    TOOL_CONTAINER_NAME = "tool_container_name"
    STATUS_HISTORY = "status_history"


@dataclass
class FileExecutionStageData:
    stage: FileExecutionStage
    status: FileExecutionStageStatus
    error: str | None = None

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        if not self.stage or not self.status:
            raise FileExecutionTrackerValueException("Stage and status are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_serializable(self) -> dict[str, Any]:
        data = {
            FileExecutionField.STAGE: self.stage.value,
            FileExecutionField.STATUS: self.status.value,
            FileExecutionField.ERROR: self.error,
        }
        # Remove any keys with value None (Redis doesn't support None in HSET)
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class FileExecutionData:
    execution_id: str
    file_execution_id: str
    organization_id: str
    stage_status: FileExecutionStageData
    status_history: list[FileExecutionStageData]
    tool_container_name: str | None = None
    error: str | None = None

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        if not self.execution_id or not self.file_execution_id:
            raise FileExecutionTrackerValueException()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_serializable(self) -> dict[str, Any]:
        data = {
            FileExecutionField.EXECUTION_ID: self.execution_id,
            FileExecutionField.FILE_EXECUTION_ID: self.file_execution_id,
            FileExecutionField.ORGANIZATION_ID: self.organization_id,
            FileExecutionField.STAGE_STATUS: json.dumps(
                self.stage_status.to_serializable()
            ),
            FileExecutionField.STATUS_HISTORY: json.dumps(
                [history.to_serializable() for history in self.status_history]
            ),
            FileExecutionField.TOOL_CONTAINER_NAME: self.tool_container_name,
            FileExecutionField.ERROR: self.error,
        }
        # Remove any keys with value None (Redis doesn't support None in HSET)
        return {k: v for k, v in data.items() if v is not None}


class FileExecutionStatusTracker:
    """File execution status tracker.

    This class is used to track the status of a file execution.
    """

    CACHE_TTL_IN_SECOND = int(
        os.environ.get("FILE_EXECUTION_TRACKER_TTL_IN_SECOND", 60 * 60 * 24)
    )

    def __init__(self):
        self.redis_client = redis.Redis(
            host=os.environ.get("REDIS_HOST"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            username=os.environ.get("REDIS_USER"),
            password=os.environ.get("REDIS_PASSWORD"),
            decode_responses=True,  # ensures hgetall returns str instead of bytes
        )

    def _resolve_field(
        self,
        field_name: str,
        new_data: FileExecutionData,
        existing_data: FileExecutionData | None,
    ) -> str:
        """Resolves the value of a field based on the new data and existing data.

        Args:
            field_name (str): Name of the field
            new_data (ToolExecutionData): New data
            existing_data (ToolExecutionData | None): Existing data

        Returns:
            str: Value of the field
        """
        new_value = getattr(new_data, field_name)
        if not new_value:
            if not existing_data:
                return ""
            new_value = getattr(existing_data, field_name)
        return new_value or ""

    def get_cache_key(self, execution_id: str, file_execution_id: str) -> str:
        return f"file_execution:{execution_id}:{file_execution_id}"

    def set_data(self, data: FileExecutionData, ttl_in_second: int | None = None) -> None:
        data.validate()
        key = self.get_cache_key(data.execution_id, data.file_execution_id)
        logger.info(f"Setting file execution data for {key}: {data.to_serializable()}")
        self.redis_client.hset(key, mapping=data.to_serializable())
        logger.info(
            f"Setting file execution data for {key} to expire in {ttl_in_second} seconds"
        )
        self.redis_client.expire(key, ttl_in_second or self.CACHE_TTL_IN_SECOND)

    def update_stage_status(
        self,
        execution_id: str,
        file_execution_id: str,
        stage_status: FileExecutionStageData,
        ttl_in_second: int | None = None,
    ) -> None:
        key = self.get_cache_key(execution_id, file_execution_id)

        # For Existing Execution Data [backward compatibility]
        if not self.redis_client.exists(key):
            self.set_data(
                FileExecutionData(
                    execution_id=execution_id,
                    file_execution_id=file_execution_id,
                    organization_id="",
                    stage_status=stage_status,
                    status_history=[stage_status],
                )
            )

        existing_data = self.get_data(
            execution_id=execution_id,
            file_execution_id=file_execution_id,
        )
        logger.info(f"Existing data for {key}: {existing_data}")
        if not existing_data:
            raise FileExecutionTrackerNotFound()

        existing_stage_status = existing_data.stage_status

        if existing_stage_status.stage == stage_status.stage:
            existing_stage_status.status = stage_status.status
            existing_stage_status.error = stage_status.error
            existing_data.stage_status = existing_stage_status

        if existing_stage_status.stage != stage_status.stage:
            # Chekck the stage order
            if not existing_stage_status.stage.can_move_to(stage_status.stage):
                raise FileExecutionStageException(
                    "Cannot move to stage: " + stage_status.stage.value
                )

            # Update stage status
            existing_data.stage_status = stage_status

            # Update status history
            existing_data.status_history = [
                existing_stage_status
            ] + existing_data.status_history
        # Update error
        existing_data.error = stage_status.error or existing_data.error
        self.set_data(existing_data, ttl_in_second)

    def update_tool_container_name(
        self, execution_id: str, file_execution_id: str, tool_container_name: str
    ) -> None:
        key = self.get_cache_key(execution_id, file_execution_id)
        with self.redis_client.pipeline() as pipe:
            pipe.hset(key, FileExecutionField.TOOL_CONTAINER_NAME, tool_container_name)
            pipe.expire(key, self.CACHE_TTL_IN_SECOND)
            pipe.execute()

    def update_error(self, execution_id: str, file_execution_id: str, error: str) -> None:
        key = self.get_cache_key(execution_id, file_execution_id)
        with self.redis_client.pipeline() as pipe:
            pipe.hset(key, FileExecutionField.ERROR, error)
            pipe.expire(key, self.CACHE_TTL_IN_SECOND)
            pipe.execute()

    def get_data(
        self, execution_id: str, file_execution_id: str
    ) -> FileExecutionData | None:
        """Get the status of a file execution.

        Args:
            execution_id (str): Execution id of the file execution
            file_execution_id (str): File execution id of the file execution

        Returns:
            FileExecutionData | None: Status of the file execution
        """
        data = self.redis_client.hgetall(
            self.get_cache_key(execution_id, file_execution_id)
        )
        if not data:
            return None

        stage_status_dict = json.loads(data.get(FileExecutionField.STAGE_STATUS, {}))
        status_history_list = json.loads(data.get(FileExecutionField.STATUS_HISTORY, []))
        return FileExecutionData(
            execution_id=execution_id,
            organization_id=data.get(FileExecutionField.ORGANIZATION_ID),
            file_execution_id=file_execution_id,
            stage_status=FileExecutionStageData(
                stage=FileExecutionStage(stage_status_dict.get(FileExecutionField.STAGE)),
                status=FileExecutionStageStatus(
                    stage_status_dict.get(FileExecutionField.STATUS)
                ),
                error=stage_status_dict.get(FileExecutionField.ERROR),
            ),
            tool_container_name=data.get(FileExecutionField.TOOL_CONTAINER_NAME),
            status_history=[
                FileExecutionStageData(
                    stage=FileExecutionStage(entry.get(FileExecutionField.STAGE)),
                    status=FileExecutionStageStatus(entry.get(FileExecutionField.STATUS)),
                    error=entry.get(FileExecutionField.ERROR),
                )
                for entry in status_history_list
            ],
            error=data.get(FileExecutionField.ERROR) or None,
        )

    def delete_data(self, execution_id: str, file_execution_id: str) -> None:
        """Delete the status of a file execution.

        Args:
            execution_id (str): Execution id of the file execution
            file_execution_id (str): File execution id of the file execution
        """
        self.redis_client.delete(self.get_cache_key(execution_id, file_execution_id))
