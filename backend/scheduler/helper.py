import logging

from django.core.exceptions import ValidationError
from scheduler import views
from scheduler.constants import SchedulerConstants as SC
from scheduler.exceptions import JobDeletionError, JobSchedulingError
from scheduler.serializer import AddJobSerializer
from scheduler.tasks import delete_periodic_task, disable_task, enable_task

logger = logging.getLogger(__name__)


class SchedulerHelper:
    @staticmethod
    def add_job(
        pipeline_id: str, cron_string: str = SC.DEFAULT_CRON_STRING
    ) -> None:
        logger.info(f"Scheduling job for {pipeline_id} with {cron_string}")
        name = f"Pipeline job-{pipeline_id}"
        job_serialize_data = {
            SC.ID: pipeline_id,
            SC.CRON_STRING: cron_string,
            SC.NAME: name,
        }
        try:
            job_serializer = AddJobSerializer(data=job_serialize_data)
            job_serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            logger.error(f"Validation error while scheduling job: {e}")
            raise JobSchedulingError
        except Exception as e:
            logger.error(f"Unhandled exception while scheduling job: {e}")
            raise JobSchedulingError

        try:
            # Celery based scheduler
            scheduler_response = views.schedule_task_job(
                pipeline_id, job_serializer.validated_data
            )
            logger.info(f"Scheduler response: {scheduler_response}")
        except Exception as e:
            logger.error(f"Exception while adding job: {e}")
            raise JobSchedulingError

    @staticmethod
    def remove_job(pipeline_id: str) -> None:
        logger.info(f"Removing job for {pipeline_id}")
        try:
            logger.info("Celery scheduler - removing job")
            delete_periodic_task(pipeline_id)
        except Exception as e:
            logger.error(f"Exception while removing job: {e}")
            raise JobDeletionError

    @staticmethod
    def pause_job(pipeline_id: str) -> None:
        logger.info(f"Pausing job for {pipeline_id}")
        try:
            logger.info("Celery scheduler - pausing job")
            disable_task(pipeline_id)
        except Exception as e:
            logger.error(f"Exception while pausing job: {e}")
            raise JobSchedulingError

    @staticmethod
    def resume_job(pipeline_id: str) -> None:
        logger.info(f"Resuming job for {pipeline_id}")
        try:
            logger.info("Celery scheduler - resuming job")
            enable_task(pipeline_id)
        except Exception as e:
            logger.error(f"Exception while resuming job: {e}")
            raise JobSchedulingError
