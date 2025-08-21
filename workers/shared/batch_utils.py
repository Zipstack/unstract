"""Batch Operations Utilities for Workers

Provides batching mechanisms to reduce individual API calls and database operations.
Optimizes callback pattern performance by aggregating multiple operations.
"""

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Any

from .enums import BatchOperationType
from .models import (
    FileStatusUpdateRequest,
    PipelineUpdateRequest,
    StatusUpdateRequest,
)
from .response_models import BatchOperationResponse, convert_dict_response

logger = logging.getLogger(__name__)


def _ensure_consistent_response(result: Any) -> BatchOperationResponse:
    """Convert any response format to consistent BatchOperationResponse."""
    if hasattr(result, "success"):
        # Already a consistent response object
        return result
    else:
        # Legacy dict response - convert to consistent format
        return convert_dict_response(result, BatchOperationResponse)


@dataclass
class BatchOperation:
    """Represents a single operation to be batched."""

    operation_type: str
    operation_id: str
    payload: dict
    callback: Callable | None = None
    created_at: float = field(default_factory=time.time)
    organization_id: str = ""
    execution_id: str = ""


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    max_batch_size: int = 10
    max_wait_time: float = 5.0  # seconds
    flush_interval: float = 2.0  # seconds
    enable_auto_flush: bool = True


class BatchProcessor:
    """Processes operations in batches to reduce API calls."""

    def __init__(self, config: BatchConfig, api_client=None):
        """Initialize batch processor.

        Args:
            config: Batch processing configuration
            api_client: API client for executing batched operations
        """
        self.config = config
        self.api_client = api_client
        self._batches: dict[str, list[BatchOperation]] = defaultdict(list)
        self._lock = Lock()
        self._running = False
        self._flush_thread = None

        # Operation handlers
        self._handlers = {
            BatchOperationType.STATUS_UPDATE: self._handle_status_update_batch,
            BatchOperationType.PIPELINE_UPDATE: self._handle_pipeline_update_batch,
            BatchOperationType.FILE_STATUS_UPDATE: self._handle_file_status_update_batch,
            "cache_invalidation": self._handle_cache_invalidation_batch,
        }

    def set_api_client(self, api_client):
        """Set the API client for batch operations."""
        self.api_client = api_client
        logger.debug("API client set for batch processor")

    def start(self):
        """Start the batch processor."""
        if self._running:
            return

        self._running = True
        if self.config.enable_auto_flush:
            self._flush_thread = Thread(target=self._auto_flush_loop, daemon=True)
            self._flush_thread.start()
            logger.info("Batch processor started with auto-flush")
        else:
            logger.info("Batch processor started without auto-flush")

    def stop(self):
        """Stop the batch processor and flush remaining operations."""
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)

        # Flush all remaining operations
        self.flush_all()
        logger.info("Batch processor stopped")

    def add_operation(
        self,
        operation_type: str,
        operation_id: str,
        payload: dict,
        organization_id: str = "",
        execution_id: str = "",
        callback: Callable | None = None,
    ) -> bool:
        """Add operation to batch queue.

        Args:
            operation_type: Type of operation to batch
            operation_id: Unique identifier for the operation
            payload: Operation data
            organization_id: Organization context
            execution_id: Execution context
            callback: Optional callback for when operation completes

        Returns:
            True if operation was added successfully
        """
        if not self._running:
            logger.warning("Batch processor not running, operation ignored")
            return False

        logger.debug(
            f"Adding operation {operation_type}:{operation_id} with payload: {payload}"
        )

        operation = BatchOperation(
            operation_type=operation_type,
            operation_id=operation_id,
            payload=payload,
            organization_id=organization_id,
            execution_id=execution_id,
            callback=callback,
        )

        with self._lock:
            batch_key = f"{operation_type}:{organization_id}"
            self._batches[batch_key].append(operation)

            logger.debug(
                f"Batch {batch_key} now has {len(self._batches[batch_key])} operations"
            )

            # Check if batch is ready for immediate processing
            if len(self._batches[batch_key]) >= self.config.max_batch_size:
                logger.debug(f"Batch full for {batch_key}, processing immediately")
                self._process_batch(batch_key)

        logger.debug(f"Added {operation_type} operation to batch")
        return True

    def flush_all(self) -> int:
        """Flush all pending batches.

        Returns:
            Number of operations processed
        """
        total_processed = 0

        with self._lock:
            batch_keys = list(self._batches.keys())

        for batch_key in batch_keys:
            processed = self._process_batch(batch_key)
            total_processed += processed

        logger.info(f"Flushed all batches, processed {total_processed} operations")
        return total_processed

    def flush_by_type(self, operation_type: str, organization_id: str = "") -> int:
        """Flush specific batch type.

        Args:
            operation_type: Type of operation to flush
            organization_id: Organization context

        Returns:
            Number of operations processed
        """
        batch_key = f"{operation_type}:{organization_id}"
        return self._process_batch(batch_key)

    def _auto_flush_loop(self):
        """Auto-flush loop running in background thread."""
        while self._running:
            try:
                time.sleep(self.config.flush_interval)

                if not self._running:
                    break

                # Check for batches that are ready to flush (by time)
                current_time = time.time()
                batches_to_flush = []

                with self._lock:
                    for batch_key, operations in self._batches.items():
                        if not operations:
                            continue

                        # Check if oldest operation exceeds wait time
                        oldest_operation = min(operations, key=lambda op: op.created_at)
                        if (
                            current_time - oldest_operation.created_at
                            >= self.config.max_wait_time
                        ):
                            batches_to_flush.append(batch_key)

                # Process batches that have timed out
                for batch_key in batches_to_flush:
                    logger.debug(f"Auto-flushing batch {batch_key} due to timeout")
                    self._process_batch(batch_key)

            except Exception as e:
                logger.error(f"Error in auto-flush loop: {e}")
                time.sleep(1.0)  # Brief pause before retrying

    def _process_batch(self, batch_key: str) -> int:
        """Process a specific batch.

        Args:
            batch_key: Key identifying the batch

        Returns:
            Number of operations processed
        """
        with self._lock:
            operations = self._batches.get(batch_key, [])
            if not operations:
                return 0

            # Remove processed operations from queue
            self._batches[batch_key] = []

        logger.debug(f"Processing batch {batch_key} with {len(operations)} operations")

        operation_type = batch_key.split(":", 1)[0]
        handler = self._handlers.get(operation_type)

        if not handler:
            logger.warning(f"No handler for operation type: {operation_type}")
            return 0

        try:
            processed_count = handler(operations)
            logger.info(f"Processed batch {batch_key}: {processed_count} operations")

            # Execute callbacks for successful operations
            for operation in operations:
                if operation.callback:
                    try:
                        operation.callback(success=True)
                    except Exception as e:
                        logger.warning(
                            f"Callback error for {operation.operation_id}: {e}"
                        )

            return processed_count

        except Exception as e:
            logger.error(f"Failed to process batch {batch_key}: {e}")

            # Execute callbacks for failed operations
            for operation in operations:
                if operation.callback:
                    try:
                        operation.callback(success=False, error=str(e))
                    except Exception as callback_error:
                        logger.warning(
                            f"Callback error for {operation.operation_id}: {callback_error}"
                        )

            return 0

    def _handle_status_update_batch(self, operations: list[BatchOperation]) -> int:
        """Handle batch of status update operations."""
        if not self.api_client:
            logger.warning("No API client configured for status updates")
            return 0

        logger.debug(f"Processing status update batch with {len(operations)} operations")

        # Group by organization for efficient API calls
        org_groups = defaultdict(list)
        for op in operations:
            logger.debug(f"Operation payload: {op.payload}")
            org_groups[op.organization_id].append(op)

        processed_count = 0

        for org_id, org_operations in org_groups.items():
            try:
                # Set organization context
                if org_id:
                    self.api_client.set_organization_context(org_id)

                # Prepare batch status update payload using dataclasses
                status_updates = []
                for op in org_operations:
                    execution_id = op.payload.get("execution_id")
                    status = op.payload.get("status")

                    logger.debug(
                        f"Processing operation: execution_id={execution_id}, status={status}, payload={op.payload}"
                    )

                    # Skip operations with missing required fields
                    if not execution_id or not status:
                        logger.warning(
                            f"Skipping status update with missing required fields: execution_id={execution_id}, status={status}"
                        )
                        continue

                    update_request = StatusUpdateRequest(
                        execution_id=execution_id,
                        status=status,
                        error_message=op.payload.get("error_message"),
                        execution_time=op.payload.get("execution_time"),
                        total_files=op.payload.get("total_files"),
                    )
                    status_updates.append(update_request.to_dict())

                logger.debug(
                    f"Prepared {len(status_updates)} status updates from {len(org_operations)} operations"
                )

                # Execute batch status update only if we have valid updates
                if not status_updates:
                    logger.warning(f"No valid status updates to process for org {org_id}")
                    continue

                result = _ensure_consistent_response(
                    self.api_client.batch_update_execution_status(status_updates)
                )

                if result.success:
                    processed_count += result.successful_items
                    logger.debug(
                        f"Batch updated {result.successful_items} statuses for org {org_id}"
                    )
                else:
                    error_msg = result.message or "Batch update failed"
                    logger.warning(
                        f"Batch status update failed for org {org_id}: {result.failed_items} failed - {error_msg}"
                    )

            except Exception as e:
                logger.error(f"Failed to batch update statuses for org {org_id}: {e}")

        return processed_count

    def _handle_pipeline_update_batch(self, operations: list[BatchOperation]) -> int:
        """Handle batch of pipeline update operations."""
        if not self.api_client:
            logger.warning("No API client configured for pipeline updates")
            return 0

        # Group by organization
        org_groups = defaultdict(list)
        for op in operations:
            org_groups[op.organization_id].append(op)

        processed_count = 0

        for org_id, org_operations in org_groups.items():
            try:
                if org_id:
                    self.api_client.set_organization_context(org_id)

                # Prepare batch pipeline update payload using dataclasses
                pipeline_updates = []
                for op in org_operations:
                    update_request = PipelineUpdateRequest(
                        pipeline_id=op.payload.get("pipeline_id"),
                        execution_id=op.payload.get("execution_id"),
                        status=op.payload.get("status"),
                        last_run_status=op.payload.get("last_run_status"),
                        last_run_time=op.payload.get("last_run_time", time.time()),
                        increment_run_count=op.payload.get("increment_run_count", False),
                    )
                    pipeline_updates.append(update_request.to_dict())

                result = _ensure_consistent_response(
                    self.api_client.batch_update_pipeline_status(pipeline_updates)
                )

                if result.success:
                    processed_count += len(org_operations)
                    logger.debug(
                        f"Batch updated {len(org_operations)} pipelines for org {org_id}"
                    )
                else:
                    error_msg = result.message or result.error or "Pipeline update failed"
                    logger.warning(
                        f"Batch pipeline update failed for org {org_id}: {error_msg}"
                    )

            except Exception as e:
                logger.error(f"Failed to batch update pipelines for org {org_id}: {e}")

        return processed_count

    def _handle_file_status_update_batch(self, operations: list[BatchOperation]) -> int:
        """Handle batch of file status update operations."""
        if not self.api_client:
            logger.warning("No API client configured for file status updates")
            return 0

        # Group by organization and execution
        execution_groups = defaultdict(list)
        for op in operations:
            key = f"{op.organization_id}:{op.execution_id}"
            execution_groups[key].append(op)

        processed_count = 0

        for group_key, group_operations in execution_groups.items():
            org_id, execution_id = group_key.split(":", 1)

            try:
                if org_id:
                    self.api_client.set_organization_context(org_id)

                # Prepare batch file status update payload using dataclasses
                file_updates = []
                for op in group_operations:
                    update_request = FileStatusUpdateRequest(
                        file_execution_id=op.payload.get("file_execution_id"),
                        status=op.payload.get("status"),
                        result=op.payload.get("result"),
                        error_message=op.payload.get("error_message"),
                        processing_time=op.payload.get("processing_time"),
                    )
                    file_updates.append(update_request.to_dict())

                result = _ensure_consistent_response(
                    self.api_client.batch_update_file_execution_status(
                        execution_id=execution_id, file_updates=file_updates
                    )
                )

                if result.success:
                    processed_count += len(group_operations)
                    logger.debug(
                        f"Batch updated {len(group_operations)} file statuses for execution {execution_id}"
                    )
                else:
                    error_msg = (
                        result.message or result.error or "File status update failed"
                    )
                    logger.warning(
                        f"Batch file status update failed for execution {execution_id}: {error_msg}"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to batch update file statuses for execution {execution_id}: {e}"
                )

        return processed_count

    def _handle_cache_invalidation_batch(self, operations: list[BatchOperation]) -> int:
        """Handle batch of cache invalidation operations."""
        # Group cache invalidations by type
        cache_keys_by_type = defaultdict(set)

        for op in operations:
            cache_type = op.payload.get("cache_type", "general")
            cache_keys = op.payload.get("cache_keys", [])
            if isinstance(cache_keys, str):
                cache_keys = [cache_keys]

            cache_keys_by_type[cache_type].update(cache_keys)

        processed_count = 0

        # Use cache manager if available
        from shared.cache_utils import get_cache_manager

        cache_manager = get_cache_manager()

        if cache_manager and cache_manager.is_available:
            try:
                for cache_type, cache_keys in cache_keys_by_type.items():
                    if cache_keys:
                        cache_manager._redis_client.delete(*list(cache_keys))
                        processed_count += len(cache_keys)
                        logger.debug(
                            f"Batch invalidated {len(cache_keys)} {cache_type} cache keys"
                        )
            except Exception as e:
                logger.error(f"Failed to batch invalidate cache: {e}")

        return processed_count

    def get_batch_stats(self) -> dict:
        """Get current batch statistics.

        Returns:
            Dictionary with batch statistics
        """
        with self._lock:
            stats = {
                "total_batches": len(self._batches),
                "total_pending_operations": sum(
                    len(ops) for ops in self._batches.values()
                ),
                "batches_by_type": {},
                "running": self._running,
                "auto_flush_enabled": self.config.enable_auto_flush,
            }

            for batch_key, operations in self._batches.items():
                operation_type = batch_key.split(":", 1)[0]
                if operation_type not in stats["batches_by_type"]:
                    stats["batches_by_type"][operation_type] = 0
                stats["batches_by_type"][operation_type] += len(operations)

        return stats


# Convenience functions for common batch operations
def add_status_update_to_batch(
    batch_processor: BatchProcessor,
    execution_id: str,
    status: str,
    organization_id: str = "",
    error_message: str = None,
    execution_time: float = None,
    total_files: int = None,
) -> bool:
    """Add status update to batch processor."""
    payload = {"execution_id": execution_id, "status": status}

    if error_message:
        payload["error_message"] = error_message
    if execution_time is not None:
        payload["execution_time"] = execution_time
    if total_files is not None:
        payload["total_files"] = total_files

    return batch_processor.add_operation(
        operation_type=BatchOperationType.STATUS_UPDATE,
        operation_id=f"status:{execution_id}:{int(time.time())}",
        payload=payload,
        organization_id=organization_id,
        execution_id=execution_id,
    )


def add_pipeline_update_to_batch(
    batch_processor: BatchProcessor,
    pipeline_id: str,
    execution_id: str,
    status: str,
    organization_id: str = "",
    last_run_status: str = None,
    last_run_time: float = None,
    increment_run_count: bool = False,
) -> bool:
    """Add pipeline update to batch processor."""
    payload = {
        "pipeline_id": pipeline_id,
        "execution_id": execution_id,
        "status": status,
        "increment_run_count": increment_run_count,
    }

    if last_run_status:
        payload["last_run_status"] = last_run_status

    if last_run_time:
        payload["last_run_time"] = last_run_time

    return batch_processor.add_operation(
        operation_type=BatchOperationType.PIPELINE_UPDATE,
        operation_id=f"pipeline:{pipeline_id}:{int(time.time())}",
        payload=payload,
        organization_id=organization_id,
        execution_id=execution_id,
    )


# Global batch processor instance
_batch_processor = None


def get_batch_processor() -> BatchProcessor | None:
    """Get global batch processor instance."""
    return _batch_processor


def initialize_batch_processor(
    config: BatchConfig = None, api_client=None
) -> BatchProcessor:
    """Initialize global batch processor."""
    global _batch_processor

    if config is None:
        config = BatchConfig()

    _batch_processor = BatchProcessor(config, api_client)
    _batch_processor.start()

    logger.info("Global batch processor initialized")
    return _batch_processor


def shutdown_batch_processor():
    """Shutdown global batch processor."""
    global _batch_processor

    if _batch_processor:
        _batch_processor.stop()
        _batch_processor = None
        logger.info("Global batch processor shutdown")
