import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import F, Q
from django.db.utils import IntegrityError
from django.utils import timezone
from utils.cache_service import CacheService

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.utils.workflow_log import WorkflowLog
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
        workflow_log: WorkflowLog | None = None,
    ) -> FileHistory | None:
        """Retrieve a file history record based on the cache key.

        First deletes expired file histories based on reprocessing interval,
        then returns the remaining file history if it exists.

        Args:
            workflow (Workflow): The workflow associated with the file history.
            cache_key (Optional[str]): The cache key to search for.
            provider_file_uuid (Optional[str]): The provider file UUID to search for.
            file_path (Optional[str]): The file path to search for.
            workflow_log (Optional[WorkflowLog]): The workflow log for user notifications.

        Returns:
            Optional[FileHistory]: The matching file history record, if found.
        """
        if not cache_key and not provider_file_uuid:
            logger.warning(
                "No cache key or provider file UUID provided "
                f"while fetching file history for {workflow}"
            )
            return None

        # Delete expired file histories before querying based on reprocessing interval
        cls._delete_expired_file_histories(workflow, workflow_log)

        filters = Q(workflow=workflow)
        if cache_key:
            filters &= Q(cache_key=cache_key)
        elif provider_file_uuid:
            filters &= Q(provider_file_uuid=provider_file_uuid)

        file_history: FileHistory | None
        try:
            if file_path:
                file_history = FileHistory.objects.get(filters & Q(file_path=file_path))
                return file_history
            file_history = FileHistory.objects.get(filters & Q(file_path__isnull=True))
            return file_history
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

    @classmethod
    def _delete_expired_file_histories(
        cls, workflow: Workflow, workflow_log: WorkflowLog | None = None
    ) -> None:
        """Delete expired file histories based on reprocessing interval from WorkflowEndpoint configuration.

        TODO: Move deletion logic to background job instead
        of calling during get_file_history().
        1. This cleanup should run periodically in the
        background (cron/Celery) rather than blocking file
        queries.
        2. Current approach impacts performance since every
        get_file_history() call triggers deletion.

        Args:
            workflow: The workflow to check for expired file histories.
            workflow_log: Optional workflow log for user notifications.
        """
        try:
            reprocessing_interval = cls._get_reprocessing_interval_from_config(
                workflow, workflow_log
            )
            if reprocessing_interval is None or reprocessing_interval <= 0:
                return  # No reprocessing configured, keep all histories

            now = timezone.now()
            expiry_date = now - timedelta(days=reprocessing_interval)
            deleted_count, _ = FileHistory.objects.filter(
                workflow=workflow, created_at__lt=expiry_date
            ).delete()

            if deleted_count > 0:
                logger.info(
                    f"Deleted {deleted_count} expired file histories for workflow {workflow.id}"
                )

        except Exception as ex:
            error_msg = (
                "Unable to clean up expired file metadata. "
                "files may not be reprocessed if its expected to. "
            )
            logger.exception(f"{error_msg}:{ex}")
            if workflow_log:
                workflow_log.log_error(logger=logger, message=error_msg)

    @staticmethod
    def _get_reprocessing_interval_from_config(
        workflow: Workflow, workflow_log: WorkflowLog | None = None
    ) -> int | None:
        """Get reprocessing interval in days from workflow configuration.

        Args:
            workflow: The workflow to get configuration from.
            workflow_log: Optional workflow log for user notifications.

        Returns:
            int | None: Reprocessing interval in days, or None if no reprocessing.
        """
        try:
            source_endpoint = WorkflowEndpoint.objects.get(
                workflow=workflow,
                endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
            )

            if not source_endpoint.configuration:
                return None

            duplicate_handling = source_endpoint.configuration.get(
                "fileReprocessingHandling"
            )
            if duplicate_handling != "reprocess_after_interval":
                return None  # Skip duplicates

            interval_value: int = source_endpoint.configuration.get(
                "reprocessInterval", 0
            )
            interval_unit: str = source_endpoint.configuration.get("intervalUnit", "days")

            if interval_value <= 0:
                return None

            # Convert to days
            if interval_unit == "months":
                return interval_value * 30
            return interval_value

        except Exception as ex:
            error_msg = (
                "Unable to fetch file metadata deletion settings, "
                "file may not be reprocessed if its expected to. "
            )
            logger.exception(f"{error_msg}:{ex}")
            if workflow_log:
                workflow_log.log_error(logger=logger, message=error_msg)
            return None

    @staticmethod
    def _safe_str(value: Any) -> str:
        """Convert value to string, return empty string if None.

        Args:
            value: Value to convert

        Returns:
            str: String representation or empty string
        """
        return str(value) if value else ""

    @staticmethod
    def _truncate_hash(file_hash: str | None) -> str:
        """Truncate hash for logging purposes.

        Args:
            file_hash: Hash string to truncate

        Returns:
            str: Truncated hash (first 16 chars) or 'None' if missing
        """
        return file_hash[:16] if file_hash else "None"

    @staticmethod
    def _increment_file_history(
        file_history: FileHistory,
        status: ExecutionStatus,
        result: Any,
        metadata: str | None,
        error: str | None,
    ) -> FileHistory:
        """Update existing file history with incremented execution count.

        Args:
            file_history: FileHistory instance to update
            status: New execution status
            result: Execution result
            metadata: Execution metadata
            error: Error message if any

        Returns:
            FileHistory: Updated file history instance
        """
        FileHistory.objects.filter(id=file_history.id).update(
            execution_count=F("execution_count") + 1,
            status=status,
            result=str(result),
            metadata=FileHistoryHelper._safe_str(metadata),
            error=FileHistoryHelper._safe_str(error),
        )
        # Refresh from DB to get updated values
        file_history.refresh_from_db()
        return file_history

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
        """Create a new file history record or increment existing one's execution count.

        This method implements execution count tracking:
        - If file history exists: increments execution_count atomically
        - If file history is new: creates with execution_count=1

        Args:
            file_hash (FileHash): The file hash for the file.
            workflow (Workflow): The associated workflow.
            status (ExecutionStatus): The execution status.
            result (Any): The result from the execution.
            metadata (str | None): The metadata from the execution.
            error (str | None): The error from the execution.
            is_api (bool): Whether this is for API workflow (affects file_path handling).

        Returns:
            FileHistory: Either newly created or updated file history record.
        """
        file_path = file_hash.file_path if not is_api else None

        # Check if file history already exists
        existing_history = FileHistoryHelper.get_file_history(
            workflow=workflow,
            cache_key=file_hash.file_hash,
            provider_file_uuid=file_hash.provider_file_uuid,
            file_path=file_path,
        )

        if existing_history:
            # File history exists - increment execution count atomically
            updated_history = FileHistoryHelper._increment_file_history(
                existing_history, status, result, metadata, error
            )
            logger.info(
                f"Updated FileHistory record (execution_count: {updated_history.execution_count}) - "
                f"file_name='{file_hash.file_name}', file_path='{file_hash.file_path}', "
                f"file_hash='{FileHistoryHelper._truncate_hash(file_hash.file_hash)}', "
                f"workflow={workflow}"
            )
            return updated_history

        # File history doesn't exist - create new record with execution_count=1
        create_data = {
            "workflow": workflow,
            "cache_key": file_hash.file_hash,
            "provider_file_uuid": file_hash.provider_file_uuid,
            "status": status,
            "result": str(result),
            "metadata": FileHistoryHelper._safe_str(metadata),
            "error": FileHistoryHelper._safe_str(error),
            "file_path": file_path,
            "execution_count": 1,
        }

        try:
            file_history = FileHistory.objects.create(**create_data)
            logger.info(
                f"Created new FileHistory record (execution_count: 1) - "
                f"file_name='{file_hash.file_name}', file_path='{file_hash.file_path}', "
                f"file_hash='{FileHistoryHelper._truncate_hash(file_hash.file_hash)}', "
                f"workflow={workflow}"
            )
            return file_history

        except IntegrityError as e:
            # Race condition: another worker created the record between our check and create
            logger.info(
                f"FileHistory constraint violation (race condition) - "
                f"file_name='{file_hash.file_name}', file_path='{file_hash.file_path}', "
                f"file_hash='{FileHistoryHelper._truncate_hash(file_hash.file_hash)}', "
                f"workflow={workflow}. Error: {e!s}"
            )

            # Retrieve the record created by another worker and increment it
            existing_record = FileHistoryHelper.get_file_history(
                workflow=workflow,
                cache_key=file_hash.file_hash,
                provider_file_uuid=file_hash.provider_file_uuid,
                file_path=file_path,
            )

            if existing_record:
                # Increment the existing record
                updated_record = FileHistoryHelper._increment_file_history(
                    existing_record, status, result, metadata, error
                )
                logger.info(
                    f"Retrieved and updated existing FileHistory record (execution_count: {updated_record.execution_count}) - "
                    f"ID: {updated_record.id}, workflow={workflow}"
                )
                return updated_record

            # This should rarely happen - existing record not found after IntegrityError
            logger.exception(
                f"Failed to retrieve existing FileHistory record after constraint violation - "
                f"file_name='{file_hash.file_name}', workflow={workflow}"
            )
            raise

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
            # Workers store file_active:* cache in Redis DB (FILE_ACTIVE_CACHE_REDIS_DB)
            DB = settings.FILE_ACTIVE_CACHE_REDIS_DB
            CacheService.clear_cache_optimized(pattern, db=DB)
            logger.info(
                f"Cleared Redis cache entries (DB {DB}) for workflow {workflow.id} with pattern: {pattern}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to clear Redis caches for workflow {workflow.id}: {str(e)}"
            )
