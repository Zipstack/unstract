import logging
import sys
from collections import defaultdict

from account.models import Organization
from celery import shared_task
from django.db import IntegrityError
from django.db.utils import ProgrammingError
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from django_tenants.utils import get_tenant_model, tenant_context
from utils.cache_service import CacheService
from utils.constants import ExecutionLogConstants
from utils.dto import LogDataDTO
from workflow_manager.workflow.models.execution_log import ExecutionLog

logger = logging.getLogger(__name__)


@shared_task(bind=True)
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

        organization_id = log_data.organization_id
        organization_logs[organization_id].append(
            ExecutionLog(
                execution_id=log_data.execution_id,
                data=log_data.data,
                event_time=log_data.event_time,
            )
        )
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
        if "migrate" not in sys.argv:
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
            name=ExecutionLogConstants.PERIODIC_TASK_NAME,
            task=ExecutionLogConstants.TASK,
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
    try:
        tenant: Organization = get_tenant_model().objects.get(
            schema_name=organization_id
        )
    except Organization.DoesNotExist:
        logger.error(f"Organization with ID {organization_id} does not exist.")
        return

    # Store the log data in the database within tenant context
    with tenant_context(tenant):
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
