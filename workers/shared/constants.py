"""Worker-specific constants without Django dependencies.
This provides the essential constants needed by workers.
Re-exports shared constants from unstract.core for consistency.
"""

# Re-export shared constants from core


class Account:
    CREATED_BY = "created_by"
    MODIFIED_BY = "modified_by"
    ORGANIZATION_ID = "organization_id"


class Common:
    METADATA = "metadata"


# ExecutionStatus is now imported from shared data models above
# This ensures consistency between backend and workers


class FileExecutionStage:
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class FileExecutionStageStatus:
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
