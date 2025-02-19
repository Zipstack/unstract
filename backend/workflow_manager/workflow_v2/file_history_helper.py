import logging
from typing import Any, Optional

from django.db.utils import IntegrityError
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class FileHistoryHelper:
    """A helper class for managing file history related operations."""

    @staticmethod
    def get_file_history(
        workflow: Workflow, cache_key: Optional[str] = None
    ) -> Optional[FileHistory]:
        """Retrieve a file history record based on the cache key.

        Args:
            cache_key (Optional[str]): The cache key to search for.

        Returns:
            Optional[FileHistory]: The matching file history record, if found.
        """
        if not cache_key:
            return None
        try:
            file_history: FileHistory = FileHistory.objects.get(
                cache_key=cache_key, workflow=workflow
            )
        except FileHistory.DoesNotExist:
            return None
        return file_history

    @staticmethod
    def create_file_history(
        cache_key: str,
        workflow: Workflow,
        status: ExecutionStatus,
        result: Any,
        metadata: Any,
        error: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> FileHistory:
        """Create a new file history record.

        Args:
            cache_key (str): The cache key for the file.
            workflow (Workflow): The associated workflow.
            status (ExecutionStatus): The execution status.
            result (Any): The result from the execution.

        Returns:
            FileHistory: The newly created file history record.
        """
        try:
            file_history: FileHistory = FileHistory.objects.create(
                workflow=workflow,
                cache_key=cache_key,
                status=status,
                result=str(result),
                metadata=str(metadata),
                error=str(error) if error else "",
            )
        except IntegrityError:
            # TODO: Need to find why duplicate insert is coming
            logger.warning(
                "Trying to insert duplication data for filename %s for workflow %s",
                file_name,
                workflow,
            )
            file_history = FileHistoryHelper.get_file_history(
                workflow=workflow, cache_key=cache_key
            )

        return file_history

    @staticmethod
    def clear_history_for_workflow(
        workflow: Workflow,
    ) -> None:
        """Clear all file history records associated with a workflow.

        Args:
            workflow (Workflow): The workflow to clear the history for.
        """
        FileHistory.objects.filter(workflow=workflow).delete()
