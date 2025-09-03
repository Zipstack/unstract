import logging
from typing import Any

from django.db.models import Q
from django.db.utils import IntegrityError
from utils.cache_service import CacheService

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class FileHistoryHelper:
    """A helper class for managing file history related operations."""

    @classmethod
    def get_file_history(
        cls,
        workflow: Workflow,
        cache_key: str | None = None,
        provider_file_uuid: str | None = None,
        file_path: str | None = None,
    ) -> FileHistory | None:
        """Retrieve a file history record based on the cache key.

        Args:
            workflow (Workflow): The workflow associated with the file history.
            cache_key (Optional[str]): The cache key to search for.
            provider_file_uuid (Optional[str]): The provider file UUID to search for.
            file_path (Optional[str]): The file path to search for.

        Returns:
            Optional[FileHistory]: The matching file history record, if found.
        """
        if not cache_key and not provider_file_uuid:
            logger.warning(
                "No cache key or provider file UUID provided "
                f"while fetching file history for {workflow}"
            )
            return None
        filters = Q(workflow=workflow)
        if cache_key:
            filters &= Q(cache_key=cache_key)
        elif provider_file_uuid:
            filters &= Q(provider_file_uuid=provider_file_uuid)

        try:
            if file_path:
                return FileHistory.objects.get(filters & Q(file_path=file_path))
            return FileHistory.objects.get(filters & Q(file_path__isnull=True))
        except FileHistory.DoesNotExist:
            if file_path:
                # Legacy fallback: file_path was not stored in older file history records; fallback ensures backward compatibility.
                return cls._fallback_file_history_lookup(
                    workflow=workflow, filters=filters
                )
            logger.info(
                f"File history not found for cache key: {cache_key}, "
                f"provider_file_uuid: {provider_file_uuid}, "
                f"file_path={file_path}, workflow={workflow}"
            )
            return None

    @classmethod
    def _fallback_file_history_lookup(
        cls, workflow: Workflow, filters: Q
    ) -> FileHistory | None:
        """Handle fallback for workflows where file_path was not stored (e.g., API deployments or older records)."""
        try:
            file_history: FileHistory = FileHistory.objects.get(
                filters & Q(file_path__isnull=True)
            )
            file_execution = cls.get_file_execution_by_file_hash(
                workflow=workflow,
                cache_key=file_history.cache_key,
                provider_file_uuid=file_history.provider_file_uuid,
            )
            if file_execution and file_execution.file_path:
                file_history.file_path = file_execution.file_path
                file_history.save(update_fields=["file_path"])
                logger.info(
                    f"[FileHistory] Backfilled file_path {file_history.file_path} for file history (workflow={workflow}, cache_key={file_history.cache_key} provider_file_uuid={file_history.provider_file_uuid})"
                )
            return file_history
        except FileHistory.DoesNotExist:
            logger.info(
                f"File history not found with filter {filters} for workflow={workflow}"
            )
            return None

    @classmethod
    def get_file_execution_by_file_hash(
        cls,
        workflow: Workflow,
        cache_key: str | None = None,
        provider_file_uuid: str | None = None,
    ) -> WorkflowFileExecution | None:
        """Retrieve file execution by file hash."""
        # Build base query conditions
        base_conditions = Q(workflow_execution__workflow=workflow)
        content_conditions = Q()
        if cache_key:
            content_conditions |= Q(file_hash=cache_key)
        elif provider_file_uuid:
            content_conditions |= Q(provider_file_uuid=provider_file_uuid)
        else:
            logger.info(
                f"File execution fetch failed due to missing cache_key and provider_file_uuid for workflow={workflow}"
            )
            return None

        # Filter file executions based on conditions
        conditions = base_conditions & content_conditions
        file_execution = WorkflowFileExecution.objects.filter(conditions).first()
        if file_execution:
            return file_execution
        logger.info(
            f"File execution not found for cache key: {cache_key}, "
            f"provider_file_uuid: {provider_file_uuid}, "
            f"workflow={workflow}"
        )
        return None

    @staticmethod
    def create_file_history(
        file_hash: FileHash,
        workflow: Workflow,
        status: ExecutionStatus,
        result: Any,
        metadata: str | None,
        error: str | None = None,
        is_api: bool = False,
    ) -> FileHistory:
        """Create a new file history record or return existing one.

        Uses atomic get-or-create pattern to handle race conditions gracefully.
        If a constraint violation occurs, attempts to retrieve the existing record.

        Args:
            file_hash (FileHash): The file hash for the file.
            workflow (Workflow): The associated workflow.
            status (ExecutionStatus): The execution status.
            result (Any): The result from the execution.
            metadata (str | None): The metadata from the execution.
            error (str | None): The error from the execution.
            is_api (bool): Whether this is for API workflow (affects file_path handling).

        Returns:
            FileHistory: Either newly created or existing file history record.
        """
        file_path = file_hash.file_path if not is_api else None

        # Prepare data for creation
        create_data = {
            "workflow": workflow,
            "cache_key": file_hash.file_hash,
            "provider_file_uuid": file_hash.provider_file_uuid,
            "status": status,
            "result": str(result),
            "metadata": str(metadata) if metadata else "",
            "error": str(error) if error else "",
            "file_path": file_path,
        }

        try:
            # Try to create the file history record
            file_history = FileHistory.objects.create(**create_data)
            logger.info(
                f"Created new FileHistory record - "
                f"file_name='{file_hash.file_name}', file_path='{file_hash.file_path}', "
                f"file_hash='{file_hash.file_hash[:16] if file_hash.file_hash else 'None'}...', "
                f"workflow={workflow}"
            )
            return file_history

        except IntegrityError as e:
            # Race condition detected - another worker created the record
            # Try to retrieve the existing record
            logger.info(
                f"FileHistory constraint violation (expected in concurrent environment) - "
                f"file_name='{file_hash.file_name}', file_path='{file_hash.file_path}', "
                f"file_hash='{file_hash.file_hash[:16] if file_hash.file_hash else 'None'}...', "
                f"workflow={workflow}. Error: {str(e)}"
            )

            # Use the existing get_file_history method to retrieve the record
            existing_record = FileHistoryHelper.get_file_history(
                workflow=workflow,
                cache_key=file_hash.file_hash,
                provider_file_uuid=file_hash.provider_file_uuid,
                file_path=file_path,
            )

            if existing_record:
                logger.info(
                    f"Retrieved existing FileHistory record after constraint violation - "
                    f"ID: {existing_record.id}, workflow={workflow}"
                )
                return existing_record
            else:
                # This should rarely happen, but if we can't find the existing record,
                # log the issue and re-raise the original exception
                logger.error(
                    f"Failed to retrieve existing FileHistory record after constraint violation - "
                    f"file_name='{file_hash.file_name}', workflow={workflow}"
                )

    @staticmethod
    def clear_history_for_workflow(
        workflow: Workflow,
    ) -> None:
        """Clear all file history records and Redis caches associated with a workflow.

        Args:
            workflow (Workflow): The workflow to clear the history for.
        """
        # Clear database records
        FileHistory.objects.filter(workflow=workflow).delete()
        logger.info(f"Cleared database records for workflow {workflow.id}")

        # Clear Redis caches for file_active entries
        pattern = f"file_active:{workflow.id}:*"

        try:
            CacheService.clear_cache(pattern)
            logger.info(
                f"Cleared Redis cache entries for workflow {workflow.id} with pattern: {pattern}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to clear Redis caches for workflow {workflow.id}: {str(e)}"
            )
