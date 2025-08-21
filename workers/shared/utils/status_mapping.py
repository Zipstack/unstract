"""Status Mapping Utilities

Map between core domain status and worker implementation status.
"""

import os
import sys

# Import shared domain models from core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core import ExecutionStatus

# Import worker enums
from ..enums import PipelineStatus


class StatusMappings:
    """Utilities for mapping between different status systems."""

    EXECUTION_TO_PIPELINE = {
        ExecutionStatus.COMPLETED: PipelineStatus.SUCCESS,
        ExecutionStatus.ERROR: PipelineStatus.FAILURE,
        ExecutionStatus.STOPPED: PipelineStatus.FAILURE,
        ExecutionStatus.EXECUTING: PipelineStatus.INPROGRESS,
        ExecutionStatus.PENDING: PipelineStatus.YET_TO_START,
        ExecutionStatus.QUEUED: PipelineStatus.YET_TO_START,  # Legacy compatibility
        ExecutionStatus.CANCELED: PipelineStatus.FAILURE,  # Legacy compatibility
    }

    PIPELINE_TO_EXECUTION = {
        PipelineStatus.SUCCESS: ExecutionStatus.COMPLETED,
        PipelineStatus.FAILURE: ExecutionStatus.ERROR,
        PipelineStatus.INPROGRESS: ExecutionStatus.EXECUTING,
        PipelineStatus.YET_TO_START: ExecutionStatus.PENDING,
        PipelineStatus.PARTIAL_SUCCESS: ExecutionStatus.COMPLETED,
    }

    @classmethod
    def execution_to_pipeline(cls, execution_status: ExecutionStatus) -> PipelineStatus:
        """Map execution status to pipeline status."""
        return cls.EXECUTION_TO_PIPELINE.get(execution_status, PipelineStatus.FAILURE)

    @classmethod
    def pipeline_to_execution(cls, pipeline_status: PipelineStatus) -> ExecutionStatus:
        """Map pipeline status to execution status."""
        return cls.PIPELINE_TO_EXECUTION.get(pipeline_status, ExecutionStatus.ERROR)

    @classmethod
    def is_final_status(cls, status: ExecutionStatus) -> bool:
        """Check if execution status is final (no further processing)."""
        return status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.ERROR,
            ExecutionStatus.STOPPED,
        ]
