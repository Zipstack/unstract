import os
from dataclasses import dataclass
from enum import Enum

import redis

from unstract.core.exceptions import (
    ToolExecutionStatusException,
    ToolExecutionValueException,
)


class ToolExecutionStatus(Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ToolExecutionField:
    EXECUTION_ID = "execution_id"
    FILE_EXECUTION_ID = "file_execution_id"
    TOOL_INSTANCE_ID = "tool_instance_id"
    ORGANIZATION_ID = "organization_id"
    STATUS = "status"
    ERROR = "error"


@dataclass
class ToolExecutionData:
    execution_id: str
    file_execution_id: str | None = None
    tool_instance_id: str | None = None
    organization_id: str | None = None
    status: ToolExecutionStatus | None = None
    error: str | None = None

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        if not self.execution_id or not self.file_execution_id:
            raise ToolExecutionValueException()


class ToolExecutionTracker:
    """Tool execution tracker.

    This class is used to track the status of a tool execution.
    """

    CACHE_TTL_IN_SECOND = int(
        os.environ.get("TOOL_EXECUTION_CACHE_TTL_IN_SECOND", 60 * 60 * 24)
    )

    def __init__(self):
        self.redis_client = redis.Redis(
            host=os.environ.get("REDIS_HOST"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            username=os.environ.get("REDIS_USER"),
            password=os.environ.get("REDIS_PASSWORD"),
            decode_responses=True,  # ensures hgetall returns str instead of bytes
        )

    def get_cache_key(self, tool_execution_data: ToolExecutionData) -> str:
        return f"tool_execution:{tool_execution_data.execution_id}:{tool_execution_data.file_execution_id}"

    def update_status(self, tool_execution_data: ToolExecutionData) -> None:
        """Update the status of a tool execution.

        Args:
            tool_execution_data (ToolExecutionData): Status of the tool execution
        """
        tool_execution_data.validate()

        try:
            status = ToolExecutionStatus(tool_execution_data.status)
        except ValueError:
            raise ToolExecutionStatusException()

        key = self.get_cache_key(tool_execution_data)
        with self.redis_client.pipeline() as pipe:
            existing_data = self.get_status(tool_execution_data)

            tool_instance_id = (
                tool_execution_data.tool_instance_id
                if tool_execution_data.tool_instance_id
                else (
                    existing_data.tool_instance_id
                    if existing_data and existing_data.tool_instance_id
                    else ""
                )
            )

            organization_id = (
                tool_execution_data.organization_id
                if tool_execution_data.organization_id
                else (
                    existing_data.organization_id
                    if existing_data and existing_data.organization_id
                    else ""
                )
            )

            error = (
                tool_execution_data.error
                if tool_execution_data.error
                else (
                    existing_data.error if existing_data and existing_data.error else ""
                )
            )
            pipe.hset(
                name=key,
                mapping={
                    ToolExecutionField.EXECUTION_ID: tool_execution_data.execution_id,
                    ToolExecutionField.FILE_EXECUTION_ID: tool_execution_data.file_execution_id,
                    ToolExecutionField.TOOL_INSTANCE_ID: tool_instance_id,
                    ToolExecutionField.ORGANIZATION_ID: organization_id,
                    ToolExecutionField.STATUS: status.value,
                    ToolExecutionField.ERROR: error,
                },
            )
            pipe.expire(key, self.CACHE_TTL_IN_SECOND)
            pipe.execute()

    def get_status(
        self, tool_execution_data: ToolExecutionData
    ) -> ToolExecutionData | None:
        """Get the status of a tool execution.

        Args:
            tool_execution_data (ToolExecutionData): Status of the tool execution

        Returns:
            ToolExecutionData | None: Status of the tool execution
        """
        tool_execution_data.validate()

        data = self.redis_client.hgetall(self.get_cache_key(tool_execution_data))
        if not data:
            return None

        return ToolExecutionData(
            tool_instance_id=data.get(ToolExecutionField.TOOL_INSTANCE_ID) or None,
            execution_id=data.get(ToolExecutionField.EXECUTION_ID) or None,
            organization_id=data.get(ToolExecutionField.ORGANIZATION_ID) or None,
            file_execution_id=data.get(ToolExecutionField.FILE_EXECUTION_ID) or None,
            status=ToolExecutionStatus(data[ToolExecutionField.STATUS])
            if data.get(ToolExecutionField.STATUS)
            else None,
            error=data.get(ToolExecutionField.ERROR) or None,
        )

    def delete_status(self, tool_execution_data: ToolExecutionData) -> None:
        """Delete the status of a tool execution.

        Args:
            tool_execution_data (ToolExecutionData): Status of the tool execution
        """
        tool_execution_data.validate()
        self.redis_client.delete(self.get_cache_key(tool_execution_data))
