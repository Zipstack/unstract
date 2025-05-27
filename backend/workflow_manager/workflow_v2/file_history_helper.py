import logging
from typing import Any

from django.db.utils import IntegrityError

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class FileHistoryHelper:
    """A helper class for managing file history related operations."""

    @staticmethod
    def get_file_history(
        workflow: Workflow,
        cache_key: str | None = None,
        provider_file_uuid: str | None = None,
    ) -> FileHistory | None:
        """Retrieve a file history record based on the cache key.

        Args:
            cache_key (Optional[str]): The cache key to search for.
            provider_file_uuid (Optional[str]): The provider file UUID to search for.

        Returns:
            Optional[FileHistory]: The matching file history record, if found.
        """
        if not cache_key and not provider_file_uuid:
            return None
        try:
            if not cache_key:
                return FileHistory.objects.get(
                    provider_file_uuid=provider_file_uuid, workflow=workflow
                )
            return FileHistory.objects.get(cache_key=cache_key, workflow=workflow)
        except FileHistory.DoesNotExist:
            return None

    @staticmethod
    def create_file_history(
        file_hash: FileHash,
        workflow: Workflow,
        status: ExecutionStatus,
        result: Any,
        metadata: str | None,
        error: str | None = None,
        file_name: str | None = None,
    ) -> None:
        """Create a new file history record.

        Args:
            cache_key (str): The cache key for the file.
            workflow (Workflow): The associated workflow.
            status (ExecutionStatus): The execution status.
            result (Any): The result from the execution.
        """
        try:
            FileHistory.objects.create(
                workflow=workflow,
                cache_key=file_hash.file_hash,
                provider_file_uuid=file_hash.provider_file_uuid,
                status=status,
                result=str(result),
                metadata=str(metadata) if metadata else "",
                error=str(error) if error else "",
            )
        except IntegrityError as e:
            # TODO: Need to find why duplicate insert is coming
            logger.warning(
                f"Trying to insert duplication data for filename {file_name} "
                f"for workflow {workflow}. Error: {str(e)} with metadata {metadata}",
            )

    @staticmethod
    def clear_history_for_workflow(
        workflow: Workflow,
    ) -> None:
        """Clear all file history records associated with a workflow.

        Args:
            workflow (Workflow): The workflow to clear the history for.
        """
        FileHistory.objects.filter(workflow=workflow).delete()
