"""Logging Message Constants

Standardized log messages for workers.
"""


class LogMessages:
    """Standardized log messages."""

    # Task lifecycle
    TASK_STARTED = "Task {task_name} started with ID {task_id}"
    TASK_COMPLETED = "Task {task_name} completed successfully in {execution_time:.2f}s"
    TASK_FAILED = "Task {task_name} failed: {error}"
    TASK_RETRYING = "Task {task_name} retrying attempt {attempt}/{max_retries}"

    # File processing
    FILE_PROCESSING_STARTED = "Started processing file batch with {file_count} files"
    FILE_PROCESSING_COMPLETED = (
        "Completed file batch processing: {successful}/{total} files successful"
    )
    FILE_EXECUTION_CREATED = "Created file execution record for {file_name}"
    FILE_STATUS_UPDATED = "Updated file execution status to {status} for {file_name}"

    # Callback processing
    CALLBACK_TRIGGERED = (
        "Callback triggered for execution {execution_id} with {batch_count} batches"
    )
    CALLBACK_AGGREGATING = "Aggregating results from {batch_count} batch executions"
    CALLBACK_STATUS_UPDATE = "Updating execution status to {status} for {execution_id}"
    CALLBACK_COMPLETED = "Callback processing completed for execution {execution_id}"

    # Cache operations
    CACHE_HIT = "Cache hit for {cache_key}"
    CACHE_MISS = "Cache miss for {cache_key}"
    CACHE_SET = "Cached data for {cache_key} with TTL {ttl}s"
    CACHE_INVALIDATED = "Invalidated cache for {cache_key}"
    CACHE_CONNECTION_LOST = "Redis connection lost, clearing potentially stale cache"

    # Health and monitoring
    WORKER_STARTED = "Worker {worker_name} started with version {version}"
    WORKER_HEALTH_OK = "Worker health check passed"
    WORKER_HEALTH_DEGRADED = "Worker health check degraded: {issues}"
    METRICS_COLLECTED = "Performance metrics collected: {metrics}"
