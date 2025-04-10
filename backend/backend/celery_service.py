"""This module contains the Celery configuration for the backend project."""

import logging
import logging.config
import os
from pprint import pformat

from celery import Celery
from utils.constants import ExecutionLogConstants

from backend.celery_task import TaskRegistry
from backend.settings.base import LOGGING

logger = logging.getLogger(__name__)

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)

# Configure logging for celery worker using same config as Django
logging.config.dictConfig(LOGGING)

# Create a Celery instance. Default time zone is UTC.
app = Celery("backend")

# Register custom tasks
TaskRegistry()

# Load task modules from all registered Django app configs.
app.config_from_object("backend.celery_config.CeleryConfig")
app.autodiscover_tasks()

logger.debug(f"Celery Configuration:\n" f"{pformat(app.conf.table(with_defaults=True))}")

# Define the queues to purge when the Celery broker is restarted.
queues_to_purge = [ExecutionLogConstants.CELERY_QUEUE_NAME]
with app.connection() as connection:
    channel = connection.channel()
    for queue_name in queues_to_purge:
        channel.queue_purge(queue_name)
