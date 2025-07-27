from __future__ import annotations

from enum import Enum

# Import shared ExecutionStatus to ensure consistency between backend and workers
from unstract.core.data_models import ExecutionStatus


class WorkflowExecutionMethod(Enum):
    INSTANT = "INSTANT"
    QUEUED = "QUEUED"

    # ExecutionStatus is now imported from shared data models above
    # This ensures consistency between backend and workers

    @classmethod
    def is_active(cls, status: str | ExecutionStatus) -> bool:
        """Check if the workflow execution status is active (in progress)."""
        try:
            status_enum = cls(status)
        except ValueError:
            raise ValueError(
                f"Invalid status: {status}. Must be a valid ExecutionStatus."
            )
        return status_enum in [cls.PENDING, cls.EXECUTING]

    @classmethod
    def get_skip_processing_statuses(cls) -> list[ExecutionStatus]:
        """Get list of statuses that should skip file processing.

        Skip processing if:
        - EXECUTING: File is currently being processed
        - PENDING: File is queued to be processed
        - COMPLETED: File has already been successfully processed

        Returns:
            list[ExecutionStatus]: List of statuses where file processing should be skipped
        """
        return [cls.EXECUTING, cls.PENDING, cls.COMPLETED]

    @classmethod
    def should_skip_file_processing(cls, status: str | ExecutionStatus) -> bool:
        """Check if file processing should be skipped based on status.

        Allow processing (retry) if:
        - STOPPED: Processing was stopped, can retry
        - ERROR: Processing failed, can retry
        """
        try:
            status_enum = cls(status)
        except ValueError:
            raise ValueError(
                f"Invalid status: {status}. Must be a valid ExecutionStatus."
            )
        return status_enum in cls.get_skip_processing_statuses()

    @classmethod
    def can_update_to_pending(cls, status: str | ExecutionStatus) -> bool:
        """Check if a status can be updated to PENDING.

        Allow updating to PENDING if:
        - Status is STOPPED or ERROR (can retry)
        - Status is None (new record)

        Don't allow updating to PENDING if:
        - Status is EXECUTING (currently processing)
        - Status is COMPLETED (already done)
        - Status is already PENDING (no change needed)
        """
        if status is None:
            return True

        try:
            status_enum = cls(status)
        except ValueError:
            return True  # Invalid status, allow update

        return status_enum in [cls.STOPPED, cls.ERROR]


class SchemaType(Enum):
    """Possible types for workflow module's JSON schema.

    Values:
        src: Refers to the source module's schema
        dest: Refers to the destination module's schema
    """

    SRC = "src"
    DEST = "dest"


class SchemaEntity(Enum):
    """Possible entities for workflow module's JSON schema.

    Values:
        file: Refers to schema for file based sources
        api: Refers to schema for API based sources
        db: Refers to schema for DB based destinations
    """

    FILE = "file"
    API = "api"
    DB = "db"


class ColumnModes(Enum):
    WRITE_JSON_TO_A_SINGLE_COLUMN = "Write JSON to a single column"
    SPLIT_JSON_INTO_COLUMNS = "Split JSON into columns"


class AgentName(Enum):
    UNSTRACT_DBWRITER = "Unstract/DBWriter"


class RuleLogic(Enum):
    AND = "AND"
    OR = "OR"


class TaskType(Enum):
    FILE_PROCESSING = "FILE_PROCESSING"
    FILE_PROCESSING_CALLBACK = "FILE_PROCESSING_CALLBACK"
