"""Filter Pipeline for File Processing

This module provides a composable filter pipeline that applies multiple filters
to file batches efficiently. Moved to shared/processing to avoid circular imports.
"""

from abc import ABC, abstractmethod
from typing import Any

from unstract.core.data_models import ExecutionStatus, FileHashData

from ..api.internal_client import InternalAPIClient
from ..cache.cache_backends import RedisCacheBackend
from ..infrastructure.logging import WorkerLogger
from ..workflow.execution.active_file_manager import ActiveFileManager

logger = WorkerLogger.get_logger(__name__)


class FileFilter(ABC):
    """Abstract base class for file filters."""

    @abstractmethod
    def apply(
        self,
        files: dict[str, FileHashData],
        context: dict[str, Any],
    ) -> dict[str, FileHashData]:
        """Apply filter to a batch of files.

        Args:
            files: Dictionary of files to filter
            context: Context containing workflow_id, execution_id, api_client, etc.

        Returns:
            Filtered dictionary of files
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this filter for logging."""
        pass


class DeduplicationFilter(FileFilter):
    """Filter to remove duplicate files within the current discovery session."""

    def __init__(self):
        self.seen_files: set[tuple[str | None, str]] = (
            set()
        )  # (provider_file_uuid, file_path)

    def apply(
        self,
        files: dict[str, FileHashData],
        context: dict[str, Any],
    ) -> dict[str, FileHashData]:
        """Remove duplicate files based on composite key (provider_uuid, path)."""
        filtered = {}

        for file_path, file_hash in files.items():
            # Create composite key (provider_file_uuid, file_path)
            composite_key = (file_hash.provider_file_uuid, file_path)

            # Check for duplicate composite key
            if composite_key in self.seen_files:
                continue

            # Add composite key to seen set
            self.seen_files.add(composite_key)

            filtered[file_path] = file_hash

        logger.debug(
            f"[DeduplicationFilter] {len(files)} → {len(filtered)} files "
            f"({len(files) - len(filtered)} duplicates removed)"
        )

        return filtered

    def get_name(self) -> str:
        return "DeduplicationFilter"


class FileHistoryFilter(FileFilter):
    """Filter files based on file history (already processed files)."""

    def __init__(self, use_file_history: bool = True):
        self.use_file_history = use_file_history
        self._cache: dict[str, bool] = {}  # Cache results to avoid duplicate API calls

    @staticmethod
    def _create_file_identifier(provider_file_uuid: str, file_path: str) -> str:
        """Create unique identifier for file in batch operations.

        Args:
            provider_file_uuid: Provider file UUID
            file_path: File path

        Returns:
            Composite identifier in format 'uuid:path'
        """
        return f"{provider_file_uuid}:{file_path}"

    @staticmethod
    def _create_cache_key(
        workflow_id: str, provider_file_uuid: str, file_path: str
    ) -> str:
        """Create composite cache key for file history caching.

        Args:
            workflow_id: Workflow ID
            provider_file_uuid: Provider file UUID
            file_path: File path

        Returns:
            Composite cache key in format 'workflow_id:uuid:path'
        """
        return f"{workflow_id}:{provider_file_uuid}:{file_path}"

    def apply(
        self,
        files: dict[str, FileHashData],
        context: dict[str, Any],
    ) -> dict[str, FileHashData]:
        """Filter out files that have already been processed."""
        if not self.use_file_history:
            return files

        workflow_id = context.get("workflow_id")
        organization_id = context.get("organization_id")
        api_client: InternalAPIClient = context.get("api_client")

        if not all([workflow_id, organization_id, api_client]):
            logger.warning(
                "[FileHistoryFilter] Missing required context, skipping filter"
            )
            return files

        filtered = {}

        # Batch check for efficiency (collect composite identifiers to avoid UUID collisions)
        identifiers_to_check = []
        identifier_to_data = {}

        for file_path, file_hash in files.items():
            if file_hash.provider_file_uuid:
                # Check cache first using composite key helper method
                cache_key = self._create_cache_key(
                    workflow_id, file_hash.provider_file_uuid, file_path
                )
                if cache_key in self._cache:
                    if not self._cache[cache_key]:  # False means not processed
                        filtered[file_path] = file_hash
                else:
                    # Use composite identifier to avoid UUID collision with different paths
                    identifier = self._create_file_identifier(
                        file_hash.provider_file_uuid, file_path
                    )
                    identifiers_to_check.append(identifier)
                    identifier_to_data[identifier] = {
                        "uuid": file_hash.provider_file_uuid,
                        "path": file_path,
                        "file_hash": file_hash,
                    }
            else:
                # Files without UUID are always included
                filtered[file_path] = file_hash

        # Process uncached identifiers in smaller batches for better performance
        if identifiers_to_check:
            logger.info(
                f"[FileHistoryFilter] Checking history for {len(identifiers_to_check)} files"
            )

            # Process all files and collect results using composite identifiers
            self._process_file_history_batch(
                identifiers_to_check=identifiers_to_check,
                identifier_to_data=identifier_to_data,
                filtered=filtered,
                workflow_id=workflow_id,
                organization_id=organization_id,
                api_client=api_client,
            )

        logger.info(
            f"[FileHistoryFilter] {len(files)} → {len(filtered)} files "
            f"({len(files) - len(filtered)} already processed)"
        )

        return filtered

    def _process_file_history_batch(
        self,
        identifiers_to_check: list[str],
        identifier_to_data: dict[str, dict[str, Any]],
        filtered: dict[str, FileHashData],
        workflow_id: str,
        organization_id: str,
        api_client: InternalAPIClient,
    ) -> None:
        """Process file history checks for a batch of composite identifiers using optimized batch API.

        This method uses the new batch file history API to check multiple files
        in a single database query, dramatically improving performance.

        Args:
            identifiers_to_check: List of composite identifiers (uuid:path format)
            identifier_to_data: Mapping of identifiers to file data {uuid, path, file_hash}
        """
        try:
            # Prepare batch request data with composite identifiers (already unique)
            batch_files = []
            for identifier in identifiers_to_check:
                data = identifier_to_data[identifier]
                batch_files.append(
                    {
                        "provider_file_uuid": data["uuid"],
                        "file_path": data["path"],
                        "identifier": identifier,  # Use composite identifier for response mapping
                    }
                )

            logger.info(
                f"[FileHistoryFilter] Making batch API call for {len(batch_files)} files"
            )

            # Single batch API call instead of N individual calls
            batch_response = api_client.get_files_history_batch(
                workflow_id=workflow_id,
                files=batch_files,
                organization_id=organization_id,
            )

            logger.info(
                f"[FileHistoryFilter] Batch API response received for {len(batch_response)} files"
            )

            # Process batch response using composite identifiers (no UUID collision!)
            for identifier in identifiers_to_check:
                data = identifier_to_data[identifier]
                uuid = data["uuid"]
                file_path = data["path"]
                file_hash = data["file_hash"]

                # Get response for this file using composite identifier (guaranteed unique)
                file_result = batch_response.get(
                    identifier, {"found": False, "is_completed": False}
                )

                logger.info(
                    f"FileHistoryFilter - Batch API response for {file_hash.file_name} (ID: {identifier}): "
                    f"found={file_result.get('found', False)}, is_completed={file_result.get('is_completed', False)}"
                )

                # Determine if file should be processed using batch result
                is_processed = self._evaluate_batch_file_history(
                    file_result=file_result,
                    file_hash=file_hash,
                    file_path=file_path,
                )

                # Cache result using composite key helper method
                cache_key = self._create_cache_key(workflow_id, uuid, file_path)
                self._cache[cache_key] = is_processed

                # Add to filtered if not processed
                if not is_processed:
                    filtered[file_path] = file_hash

        except Exception as e:
            logger.error(
                f"FileHistoryFilter - Error processing batch file history: {e}",
                exc_info=True,
            )
            raise e

    def _evaluate_file_history(
        self,
        history_response,
        file_hash: FileHashData,
        file_path: str,
    ) -> bool:
        """Evaluate if a file should be considered as already processed.

        Returns:
            True if file should be skipped (already processed), False if should be processed
        """
        if (
            not history_response
            or not history_response.success
            or not history_response.found
        ):
            return False

        file_history = history_response.file_history
        if not file_history:
            logger.warning(
                f"FileHistoryFilter - {file_hash.file_name}: Found=True but no file_history data!"
            )
            return False

        # Check using proper status-based logic instead of just is_completed
        status = file_history.get("status", "UNKNOWN")
        is_completed = file_history.get("is_completed", False)

        logger.info(
            f"FileHistoryFilter - Evaluating {file_hash.file_name} "
            f"(UUID: {file_hash.provider_file_uuid}): found=True, is_completed={is_completed}, status={status}"
        )

        # Import ExecutionStatus for proper status checking

        # Check if file should be skipped based on status
        try:
            if status in [
                ExecutionStatus.EXECUTING.value,
                ExecutionStatus.PENDING.value,
                ExecutionStatus.COMPLETED.value,
            ]:
                logger.info(
                    f"FileHistoryFilter - {file_hash.file_name}: Status check: SKIP "
                    f"(status={status} is in skip-processing list)"
                )
            else:
                logger.info(
                    f"FileHistoryFilter - {file_hash.file_name}: Status check: ACCEPT "
                    f"(status={status} allows reprocessing)"
                )
                return False
        except Exception as e:
            logger.warning(f"FileHistoryFilter - Error checking status {status}: {e}")
            # Fallback to original is_completed logic if status checking fails
            if not is_completed:
                logger.info(
                    f"FileHistoryFilter - {file_hash.file_name}: ACCEPT "
                    f"(fallback: history exists but not completed, status={status})"
                )
                return False

        # If we reach here, should_skip is True (status is in skip list)
        # Now check path matching - only skip if paths match
        history_path = file_history.get("file_path")

        if history_path == file_path:
            logger.info(
                f"FileHistoryFilter - {file_hash.file_name}: SKIP "
                f"(status={status} requires skip and same path: {file_path})"
            )
            return True
        else:
            logger.info(
                f"FileHistoryFilter - {file_hash.file_name}: ACCEPT "
                f"(status={status} but different path: {history_path} vs {file_path})"
            )
            return False

    def _evaluate_batch_file_history(
        self,
        file_result: dict[str, Any],
        file_hash: FileHashData,
        file_path: str,
    ) -> bool:
        """Evaluate if a file should be considered as already processed using batch API result.

        Args:
            file_result: Result from batch API call
            file_hash: FileHashData object
            file_path: File path

        Returns:
            True if file should be skipped (already processed), False if should be processed
        """
        # Enhanced debug logging to trace evaluation flow
        found = file_result.get("found", False)
        is_completed = file_result.get("is_completed", False)
        file_history = file_result.get("file_history", {})

        logger.info(
            f"FileHistoryFilter - Evaluating {file_hash.file_name} "
            f"(UUID: {file_hash.provider_file_uuid}): found={found}, is_completed={is_completed}"
        )

        if not found:
            return False

        # Extract detailed status information from file history
        if file_history:
            status = file_history.get("status", "UNKNOWN")
            history_path = file_history.get("file_path")
            execution_count = file_history.get("execution_count", 0)
            max_execution_count = file_history.get("max_execution_count", 3)
            has_exceeded_limit = file_history.get("has_exceeded_limit")
            logger.info(
                f"FileHistoryFilter - {file_hash.file_name}: History details: "
                f"status={status}, path={history_path}, current_path={file_path}, "
                f"execution_count={execution_count}/{max_execution_count}, "
                f"has_exceeded_limit={has_exceeded_limit}"
            )

            # Check execution limit using backend's has_exceeded_limit flag
            # Backend determines if limit applies based on workflow type (e.g., API workflows are exempt)
            # Prefer backend's flag; only fall back to raw count if flag is not provided
            if has_exceeded_limit is True:
                logger.warning(
                    f"FileHistoryFilter - {file_hash.file_name}: SKIP "
                    f"(backend reports has_exceeded_limit=True)"
                )
                return True  # Skip file - backend determined limit exceeded
            elif (
                has_exceeded_limit is None
                and max_execution_count is not None
                and execution_count >= max_execution_count
            ):
                # Backward compatibility: if backend doesn't provide has_exceeded_limit flag,
                # fall back to raw count comparison
                logger.warning(
                    f"FileHistoryFilter - {file_hash.file_name}: SKIP "
                    f"(max execution count reached: {execution_count}/{max_execution_count})"
                )
                return True  # Skip file - max execution count exceeded
        else:
            logger.warning(
                f"FileHistoryFilter - {file_hash.file_name}: Found=True but no file_history data!"
            )

        # Check using proper status-based logic
        status = (
            file_history.get("status", "UNKNOWN") if file_history else "NO_HISTORY_DATA"
        )

        # If status allows reprocessing, accept immediately
        if status not in [
            ExecutionStatus.EXECUTING.value,
            ExecutionStatus.PENDING.value,
            ExecutionStatus.COMPLETED.value,
        ]:
            logger.info(
                f"FileHistoryFilter - {file_hash.file_name}: ACCEPT "
                f"(status={status} allows reprocessing)"
            )
            return False

        # Status requires skip check - only skip if path also matches
        history_path = file_history.get("file_path") if file_history else None

        if history_path == file_path:
            logger.info(
                f"FileHistoryFilter - {file_hash.file_name}: SKIP "
                f"(status={status} and same path: {file_path})"
            )
            return True
        else:
            logger.info(
                f"FileHistoryFilter - {file_hash.file_name}: ACCEPT "
                f"(status={status} but different path: {history_path} vs {file_path})"
            )
            return False

    def _process_file_history_individual(
        self,
        identifiers_to_check: list[str],
        identifier_to_data: dict[str, dict[str, Any]],
        filtered: dict[str, FileHashData],
        workflow_id: str,
        organization_id: str,
        api_client: InternalAPIClient,
    ) -> None:
        """Fallback method for individual file history checks when batch API fails.

        This method processes files one by one using the original individual API calls.
        Used as a backup when the batch API is unavailable or fails.

        Args:
            identifiers_to_check: List of composite identifiers (uuid:path format)
            identifier_to_data: Mapping of identifiers to file data {uuid, path, file_hash}
        """
        logger.info(
            f"[FileHistoryFilter] Processing {len(identifiers_to_check)} files individually (fallback mode)"
        )

        for identifier in identifiers_to_check:
            data = identifier_to_data[identifier]
            uuid = data["uuid"]
            file_path = data["path"]
            file_hash = data["file_hash"]

            try:
                # Check file history via individual API call
                history_response = api_client.get_file_history(
                    workflow_id=workflow_id,
                    provider_file_uuid=uuid,
                    file_path=file_path,
                    organization_id=organization_id,
                )

                logger.info(
                    f"FileHistoryFilter - Individual API response for {file_hash.file_name}: "
                    f"success={history_response.success if history_response else 'None'}"
                )

                # Determine if file should be processed
                is_processed = self._evaluate_file_history(
                    history_response=history_response,
                    file_hash=file_hash,
                    file_path=file_path,
                )

                # Cache result using composite key helper method
                cache_key = self._create_cache_key(workflow_id, uuid, file_path)
                self._cache[cache_key] = is_processed

                # Add to filtered if not processed
                if not is_processed:
                    filtered[file_path] = file_hash

            except Exception as e:
                logger.warning(
                    f"[FileHistoryFilter] Error checking individual history for {uuid}: {e}"
                )
                # On error, include the file (fail-safe approach)
                filtered[file_path] = file_hash

    def get_name(self) -> str:
        return "FileHistoryFilter"


class ActiveFileFilter(FileFilter):
    """Filter files that are currently being processed by other executions."""

    def __init__(self):
        self._cache_checked: set[str] = (
            set()
        )  # Track composite identifiers we've already checked

    @staticmethod
    def _create_file_identifier(provider_file_uuid: str, file_path: str) -> str:
        """Create unique identifier for file in active checking.

        Args:
            provider_file_uuid: Provider file UUID
            file_path: File path

        Returns:
            Composite identifier in format 'uuid:path'
        """
        return f"{provider_file_uuid}:{file_path}"

    def apply(
        self,
        files: dict[str, FileHashData],
        context: dict[str, Any],
    ) -> dict[str, FileHashData]:
        """Filter out files being processed by other executions."""
        workflow_id = context.get("workflow_id")
        execution_id = context.get("execution_id")
        api_client = context.get("api_client")

        if not all([workflow_id, execution_id, api_client]):
            logger.warning("[ActiveFileFilter] Missing required context, skipping filter")
            return files

        # Extract file identifiers for batch checking (avoid UUID collision)
        file_identifiers = {}  # identifier -> {uuid, path, file_hash}
        for file_path, file_hash in files.items():
            if file_hash.provider_file_uuid:
                identifier = self._create_file_identifier(
                    file_hash.provider_file_uuid, file_path
                )
                file_identifiers[identifier] = {
                    "uuid": file_hash.provider_file_uuid,
                    "path": file_path,
                    "file_hash": file_hash,
                }

        if not file_identifiers:
            logger.info("ActiveFileFilter - No files with provider_uuid, accepting all")
            return files

        # Batch check active files (cache + database) using composite identifiers
        active_identifiers = self._check_active_files_batch(
            file_identifiers=file_identifiers,
            workflow_id=workflow_id,
            execution_id=execution_id,
            api_client=api_client,
        )

        # Filter out active files using composite identifier matching
        filtered = {}
        for identifier, data in file_identifiers.items():
            file_hash = data["file_hash"]
            file_path = data["path"]

            if identifier in active_identifiers:
                # Skip active files
                pass
            else:
                filtered[file_path] = file_hash

        # Also include files without provider_file_uuid (they were not in file_identifiers)
        for file_path, file_hash in files.items():
            if not file_hash.provider_file_uuid and file_path not in filtered:
                filtered[file_path] = file_hash

        logger.info(
            f"[ActiveFileFilter] {len(files)} → {len(filtered)} files "
            f"({len(active_identifiers)} currently active) for execution_id {execution_id}"
        )

        return filtered

    def _check_active_files_batch(
        self,
        file_identifiers: dict[str, dict[str, Any]],
        workflow_id: str,
        execution_id: str,
        api_client,  # Removed type hint to avoid import
    ) -> set[str]:
        """Check which files are currently active (cache + database) using composite identifiers.

        Args:
            file_identifiers: Dict mapping composite identifiers to file data

        Returns:
            Set of composite identifiers that are currently active
        """
        active_identifiers = set()

        # Filter out already checked identifiers
        identifiers_to_check = [
            identifier
            for identifier in file_identifiers.keys()
            if identifier not in self._cache_checked
        ]

        if not identifiers_to_check:
            return active_identifiers

        # 1. Check Redis cache for active files using precise cache keys
        try:
            cache = RedisCacheBackend()
            for identifier in identifiers_to_check:
                data = file_identifiers[identifier]
                uuid = data["uuid"]
                file_path = data["path"]

                # Create precise cache key using same hashing logic as ActiveFileManager
                cache_key = ActiveFileManager._create_cache_key(
                    workflow_id, uuid, file_path
                )
                cached_data = cache.get(cache_key)

                if cached_data and isinstance(cached_data, dict):
                    cached_exec_id = cached_data.get("data", {}).get("execution_id")
                    if cached_exec_id and cached_exec_id != execution_id:
                        active_identifiers.add(identifier)
                        logger.debug(
                            f"[ActiveFileFilter] File {identifier} active in cache (exec: {cached_exec_id})"
                        )
        except Exception as e:
            logger.warning(f"[ActiveFileFilter] Cache check failed: {e}")

        logger.info(
            f"[ActiveFileFilter] found {len(active_identifiers)} from cache for execution {execution_id}"
        )
        # 2. Check database for active files (only files not found in cache)
        try:
            # Filter out files already found active in cache to reduce DB query size
            remaining_identifiers = [
                identifier
                for identifier in identifiers_to_check
                if identifier not in active_identifiers
            ]

            if not remaining_identifiers:
                logger.info(
                    f"[ActiveFileFilter] All files already checked via cache, skipping database check for execution_id {execution_id}"
                )
            else:
                logger.info(
                    f"[ActiveFileFilter] Checking {len(remaining_identifiers)} remaining files in database "
                    f"({len(active_identifiers)} already found in cache) for execution_id {execution_id}"
                )

                # Prepare composite file information for the API call
                files_for_api = []
                for identifier in remaining_identifiers:
                    data = file_identifiers[identifier]
                    files_for_api.append({"uuid": data["uuid"], "path": data["path"]})

                response = api_client.check_files_active_processing(
                    workflow_id=workflow_id,
                    files=files_for_api,
                    current_execution_id=execution_id,
                )

                if response.success and response.data:
                    # Backend returns: {"active_files": {uuid: [exec_data]}, "active_uuids": [uuid1, uuid2], "active_identifiers": ["uuid:path"]}
                    # Use the new composite identifiers if available, fallback to legacy format
                    active_composite_ids = response.data.get("active_identifiers", [])
                    if active_composite_ids:
                        # New path-aware format
                        logger.debug(
                            f"[ActiveFileFilter] Backend reported {len(active_composite_ids)} active identifiers: {active_composite_ids}"
                        )
                        for composite_id in active_composite_ids:
                            if composite_id in remaining_identifiers:
                                active_identifiers.add(composite_id)
                                logger.debug(
                                    f"[ActiveFileFilter] File {composite_id} active in database"
                                )
                    else:
                        # Fallback to legacy format
                        active_uuids = response.data.get("active_uuids", [])
                        logger.debug(
                            f"[ActiveFileFilter] Backend reported {len(active_uuids)} active UUIDs (legacy): {active_uuids}"
                        )

                        # Map back to identifiers
                        for identifier in remaining_identifiers:
                            data = file_identifiers[identifier]
                            uuid = data["uuid"]

                            if uuid in active_uuids:
                                active_identifiers.add(identifier)
                                logger.debug(
                                    f"[ActiveFileFilter] File {identifier} active in database (legacy mapping)"
                                )
        except Exception as e:
            logger.warning(f"[ActiveFileFilter] Database check failed: {e}")

        # Mark these identifiers as checked
        self._cache_checked.update(identifiers_to_check)

        return active_identifiers

    def get_name(self) -> str:
        return "ActiveFileFilter"


class FilterPipeline:
    """Composable pipeline of file filters."""

    def __init__(self, filters: list[FileFilter] | None = None):
        """Initialize filter pipeline.

        Args:
            filters: List of filters to apply in order
        """
        self.filters = filters or []
        logger.info(
            f"[FilterPipeline] Initialized with {len(self.filters)} filters: "
            f"{[f.get_name() for f in self.filters]}"
        )

    def add_filter(self, filter: FileFilter) -> None:
        """Add a filter to the pipeline."""
        self.filters.append(filter)
        logger.debug(f"[FilterPipeline] Added filter: {filter.get_name()}")

    def apply_filters(
        self,
        files: dict[str, FileHashData],
        workflow_id: str,
        execution_id: str,
        api_client,  # Removed type hint to avoid import
        organization_id: str | None = None,
    ) -> dict[str, FileHashData]:
        """Apply all filters in the pipeline to the files.

        Args:
            files: Dictionary of files to filter
            workflow_id: Workflow ID
            execution_id: Execution ID
            api_client: API client for backend calls
            organization_id: Organization ID

        Returns:
            Filtered dictionary of files
        """
        if not self.filters:
            return files

        # Build context for filters
        context = {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "api_client": api_client,
            "organization_id": organization_id,
        }

        filtered = files
        initial_count = len(files)

        # Apply each filter in sequence
        for filter in self.filters:
            if not filtered:  # Early exit if no files left
                break

            before_count = len(filtered)
            filtered = filter.apply(filtered, context)
            after_count = len(filtered)

            if before_count != after_count:
                logger.debug(
                    f"[FilterPipeline] {filter.get_name()}: {before_count} → {after_count} files"
                )

        if initial_count != len(filtered):
            logger.info(
                f"[FilterPipeline] Total filtering: {initial_count} → {len(filtered)} files "
                f"({initial_count - len(filtered)} filtered out)"
            )

        return filtered


def create_standard_pipeline(
    use_file_history: bool = True,
    enable_active_filtering: bool = True,
) -> FilterPipeline:
    """Create a standard filter pipeline with common filters.

    Args:
        use_file_history: Whether to use file history filtering
        enable_active_filtering: Whether to filter active files

    Returns:
        Configured FilterPipeline
    """
    filters = [
        DeduplicationFilter(),  # Always remove duplicates
    ]

    if use_file_history:
        filters.append(FileHistoryFilter(use_file_history=True))

    if enable_active_filtering:
        filters.append(ActiveFileFilter())

    return FilterPipeline(filters=filters)
