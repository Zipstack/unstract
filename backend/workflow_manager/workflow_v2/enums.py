from __future__ import annotations

from enum import Enum

from django.db.models import TextChoices


class WorkflowExecutionMethod(Enum):
    INSTANT = "INSTANT"
    QUEUED = "QUEUED"


class ExecutionStatus(TextChoices):
    """An enumeration representing the various statuses of an execution
    process.

    Statuses:
        PENDING: The execution's entry has been created in the database.
        EXECUTING: The execution is currently in progress.
        COMPLETED: The execution has been successfully completed.
        STOPPED: The execution was stopped by the user
            (applicable to step executions).
        ERROR: An error occurred during the execution process.

    Note:
        Intermediate statuses might not be experienced due to
        Django's query triggering once all processes are completed.
    """

    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

    @classmethod
    def is_completed(cls, status: str | ExecutionStatus) -> bool:
        """Check if the execution status is completed."""
        try:
            status_enum = cls(status)
        except ValueError:
            raise ValueError(
                f"Invalid status: {status}. Must be a valid ExecutionStatus."
            )
        return status_enum in [cls.COMPLETED, cls.STOPPED, cls.ERROR]

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
