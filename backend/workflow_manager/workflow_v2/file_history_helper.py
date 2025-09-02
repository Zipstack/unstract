import logging
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.db.utils import IntegrityError
from django.utils import timezone

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
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

        First deletes expired file histories based on reprocessing interval,
        then returns the remaining file history if it exists.

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

        # Delete expired file histories before querying
        cls._delete_expired_file_histories(workflow)

        filters = Q(workflow=workflow)
        if cache_key:
            filters &= Q(cache_key=cache_key)
        elif provider_file_uuid:
            filters &= Q(provider_file_uuid=provider_file_uuid)

        try:
            if file_path:
                file_history: FileHistory = FileHistory.objects.get(
                    filters & Q(file_path=file_path)
                )
            else:
                file_history: FileHistory = FileHistory.objects.get(
                    filters & Q(file_path__isnull=True)
                )
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
    def _delete_expired_file_histories(cls, workflow: Workflow) -> None:
        """Delete expired file histories based on reprocessing interval from WorkflowEndpoint configuration.

        Args:
            workflow: The workflow to check for expired file histories.
        """
        try:
            reprocessing_interval = cls._get_reprocessing_interval_from_config(workflow)
            if reprocessing_interval is None or reprocessing_interval <= 0:
                return  # No reprocessing configured, keep all histories

            now = timezone.now()
            expiry_date = now - timedelta(days=reprocessing_interval)

            print(
                f"####### Deleting expired file histories ######### workflow={workflow}, interval={reprocessing_interval} days, expiry_date={expiry_date}"
            )

            # Delete file histories that are older than the reprocessing interval
            deleted_count, _ = FileHistory.objects.filter(
                workflow=workflow, created_at__lt=expiry_date
            ).delete()

            if deleted_count > 0:
                logger.info(
                    f"Deleted {deleted_count} expired file histories for workflow {workflow}"
                )

        except Exception as e:
            logger.error(
                f"Error deleting expired file histories for workflow {workflow}: {e}"
            )

    @staticmethod
    def _get_reprocessing_interval_from_config(workflow: Workflow) -> int | None:
        """Get reprocessing interval in days from workflow configuration.

        Args:
            workflow: The workflow to get configuration from.

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
            print("####### interval_value ####### ", interval_value)
            return interval_value

        except Exception as e:
            logger.error(
                f"Error getting reprocessing interval for workflow {workflow}: {e}"
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
    ) -> None:
        """Create a new file history record.

        Args:
            file_hash (FileHash): The file hash for the file.
            workflow (Workflow): The associated workflow.
            status (ExecutionStatus): The execution status.
            result (Any): The result from the execution.
            metadata (str | None): The metadata from the execution.
            error (str | None): The error from the execution.
            is_api (bool): Whether this is an API call.
        """
        try:
            file_path = file_hash.file_path if not is_api else None

            FileHistory.objects.create(
                workflow=workflow,
                cache_key=file_hash.file_hash,
                provider_file_uuid=file_hash.provider_file_uuid,
                status=status,
                result=str(result),
                metadata=str(metadata) if metadata else "",
                error=str(error) if error else "",
                file_path=file_path,
            )
        except IntegrityError as e:
            # TODO: Need to find why duplicate insert is coming
            logger.warning(
                f"Trying to insert duplication data for filename {file_hash.file_name} "
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
