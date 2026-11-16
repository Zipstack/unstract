"""File processing context and state models.

This module contains data structures related to file processing
that are shared across worker modules.
"""

import time
from typing import Any

# Note: We're not importing these here to avoid potential circular dependencies
# They will be injected via constructor parameters
# from unstract.api.internal_client import InternalAPIClient
# from unstract.infrastructure.logging.workflow_logger import WorkerWorkflowLogger
from shared.infrastructure.logging import WorkerLogger

from unstract.core.data_models import FileHashData, WorkerFileData

logger = WorkerLogger.get_logger(__name__)


class FileProcessingContext:
    """Container for file processing context and state."""

    def __init__(
        self,
        file_data: WorkerFileData,
        file_hash: FileHashData,
        api_client: Any,  # Type as Any to avoid import dependency
        workflow_execution: dict[str, Any],
        workflow_file_execution_id: str = None,
        workflow_file_execution_object: Any = None,
        workflow_logger: Any = None,  # Type as Any to avoid import dependency
        current_file_idx: int = 1,
        total_files: int = 1,
    ):
        self.file_data = file_data
        self.file_hash = file_hash
        self.api_client = api_client
        self.workflow_execution = workflow_execution
        self.workflow_file_execution_id = workflow_file_execution_id
        self.workflow_file_execution_object = workflow_file_execution_object
        self.workflow_logger = workflow_logger
        self.current_file_idx = current_file_idx
        self.total_files = total_files

        # Extract common identifiers
        self.execution_id = file_data.execution_id
        self.workflow_id = file_data.workflow_id
        self.organization_id = file_data.organization_id
        self.use_file_history = getattr(file_data, "use_file_history", True)

        self.file_name = file_hash.file_name or "unknown"
        self.file_start_time = time.time()

        logger.info(
            f"[Execution {self.execution_id}] Processing file: '{self.file_name}'"
        )

    @property
    def is_api_workflow(self) -> bool:
        """Check if this is an API workflow based on file path."""
        return self.file_hash.file_path and "/api/" in self.file_hash.file_path

    def get_processing_duration(self) -> float:
        """Get the processing duration in seconds."""
        return time.time() - self.file_start_time
