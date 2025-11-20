import logging
import sys
from collections import defaultdict

from celery import shared_task
from django.db import IntegrityError
from django.db.utils import ProgrammingError
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from utils.cache_service import CacheService
from utils.constants import ExecutionLogConstants
from utils.dto import LogDataDTO

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models import ExecutionLog, WorkflowExecution

logger = logging.getLogger(__name__)


def process_log_history_from_cache(
    queue_name: str = ExecutionLogConstants.LOG_QUEUE_NAME,
    batch_limit: int = ExecutionLogConstants.LOGS_BATCH_LIMIT,
) -> dict:
    """Process log history from Redis cache.

    This function contains the core business logic for processing execution logs
    from Redis cache to database. It can be called by both the Celery task and
    internal API endpoints.

    Args:
        queue_name: Redis queue name to process logs from
        batch_limit: Maximum number of logs to process in one batch

    Returns:
        Dictionary with processing results:
        - processed_count: Number of logs successfully stored
        - skipped_count: Number of logs skipped (invalid references)
        - total_logs: Total number of logs retrieved from cache
        - organizations_processed: Number of organizations affected
    """
    organization_logs = defaultdict(list)
    logs_count = 0
    logs_to_process = []
    skipped_count = 0

    # Collect logs from cache (batch retrieval)
    while logs_count < batch_limit:
        log = CacheService.lpop(queue_name)
        if not log:
            break

        log_data: LogDataDTO | None = LogDataDTO.from_json(log)
        if log_data:
            logs_to_process.append(log_data)
            logs_count += 1

    if not logs_to_process:
        return {
            "processed_count": 0,
            "skipped_count": 0,
            "total_logs": 0,
            "organizations_processed": 0,
        }

    logger.info(f"Processing {logs_count} logs from queue '{queue_name}'")

    # Preload required WorkflowExecution and WorkflowFileExecution objects
    execution_ids = {log.execution_id for log in logs_to_process}
    file_execution_ids = {
        log.file_execution_id for log in logs_to_process if log.file_execution_id
    }

    execution_map = {
        str(obj.id): obj for obj in WorkflowExecution.objects.filter(id__in=execution_ids)
    }
    file_execution_map = {
        str(obj.id): obj
        for obj in WorkflowFileExecution.objects.filter(id__in=file_execution_ids)
    }

    # Process logs with preloaded data
    for log_data in logs_to_process:
        execution = execution_map.get(log_data.execution_id)
        if not execution:
            logger.warning(
                f"Execution not found for execution_id: {log_data.execution_id}, "
                "skipping log push"
            )
            skipped_count += 1
            continue

        execution_log = ExecutionLog(
            wf_execution=execution,
            data=log_data.data,
            event_time=log_data.event_time,
        )

        if log_data.file_execution_id:
            file_execution = file_execution_map.get(log_data.file_execution_id)
            if file_execution:
                execution_log.file_execution = file_execution
            else:
                logger.warning(
                    f"File execution not found for file_execution_id: {log_data.file_execution_id}, "
                    "skipping log push"
                )
                skipped_count += 1
                continue

        organization_logs[log_data.organization_id].append(execution_log)

    # Bulk insert logs for each organization
    processed_count = 0
    for organization_id, logs in organization_logs.items():
        logger.info(f"Storing {len(logs)} logs for org: {organization_id}")
        ExecutionLog.objects.bulk_create(objs=logs, ignore_conflicts=True)
        processed_count += len(logs)

    return {
        "processed_count": processed_count,
        "skipped_count": skipped_count,
        "total_logs": logs_count,
        "organizations_processed": len(organization_logs),
    }


@shared_task(name=ExecutionLogConstants.TASK_V2)
def consume_log_history() -> None:
    """Celery task to consume log history from Redis cache.

    This task is a thin wrapper around process_log_history_from_cache() for
    backward compatibility with existing Celery Beat schedules.
    """
    process_log_history_from_cache()


def create_log_consumer_scheduler_if_not_exists() -> None:
    try:
        interval, _ = IntervalSchedule.objects.get_or_create(
            every=ExecutionLogConstants.CONSUMER_INTERVAL,
            period=IntervalSchedule.SECONDS,
        )
    except ProgrammingError as error:
        logger.warning(
            "ProgrammingError occurred while creating "
            "log consumer scheduler. If you are currently running "
            "migrations for new environment, you can ignore this warning"
        )
        if all(arg not in sys.argv for arg in ("migrate", "makemigrations")):
            logger.warning(f"ProgrammingError details: {error}")
        return
    except IntervalSchedule.MultipleObjectsReturned as error:
        logger.error(f"Error occurred while getting interval schedule: {error}")
        interval = IntervalSchedule.objects.filter(
            every=ExecutionLogConstants.CONSUMER_INTERVAL,
            period=IntervalSchedule.SECONDS,
        ).first()
    try:
        # Create the scheduler
        task, created = PeriodicTask.objects.get_or_create(
            name=ExecutionLogConstants.PERIODIC_TASK_NAME_V2,
            task=ExecutionLogConstants.TASK_V2,
            defaults={
                "interval": interval,
                "queue": ExecutionLogConstants.CELERY_QUEUE_NAME,
                "enabled": ExecutionLogConstants.IS_ENABLED,
            },
        )
        if not created:
            task.enabled = ExecutionLogConstants.IS_ENABLED
            task.interval = interval
            task.queue = ExecutionLogConstants.CELERY_QUEUE_NAME
            task.save()
            logger.info("Log consumer scheduler updated successfully.")
        else:
            logger.info("Log consumer scheduler created successfully.")
    except IntegrityError as error:
        logger.error(f"Error occurred while creating log consumer scheduler: {error}")
