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
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, name=ExecutionLogConstants.TASK_V2)
def consume_log_history(self):
    organization_logs = defaultdict(list)
    logs_count = 0

    while logs_count < ExecutionLogConstants.LOGS_BATCH_LIMIT:
        log = CacheService.lpop(ExecutionLogConstants.LOG_QUEUE_NAME)
        if not log:
            break

        log_data = LogDataDTO.from_json(log)
        if not log_data:
            continue

        # Create ExecutionLog instance
        execution_log = ExecutionLog(
            execution_id=log_data.execution_id,
            data=log_data.data,
            event_time=log_data.event_time,
        )

        # Conditionally set file_execution if file_execution_id is present
        if log_data.file_execution_id:
            execution_log.file_execution = WorkflowFileExecution(
                id=log_data.file_execution_id
            )

        organization_id = log_data.organization_id
        organization_logs[organization_id].append(execution_log)
        logs_count += 1
    logger.info(f"Logs count: {logs_count}")
    for organization_id, logs in organization_logs.items():
        store_to_db(organization_id, logs)


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


def store_to_db(organization_id: str, execution_logs: list[ExecutionLog]) -> None:

    # Store the log data in the database within tenant context
    ExecutionLog.objects.bulk_create(objs=execution_logs, ignore_conflicts=True)


class ExecutionLogUtils:

    @staticmethod
    def get_execution_logs_by_execution_id(execution_id) -> list[ExecutionLog]:
        """Get all execution logs for a given execution ID.

        Args:
            execution_id (int): The ID of the execution.

        Returns:
            list[ExecutionLog]: A list of ExecutionLog objects.
        """
        return ExecutionLog.objects.filter(execution_id=execution_id)
