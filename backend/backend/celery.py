"""This module contains the Celery configuration for the backend project."""

import os

from dotenv import find_dotenv, load_dotenv

# NOTE:
# Do this before loading any environment variables.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.celery"),
)

# Load environment variables.
load_dotenv(find_dotenv() or "")

from celery import Celery  # noqa: E402
from django.conf import settings  # noqa: E402
from utils.celery.constants import ExecutionLogConstants  # noqa: E402
from utils.celery.task_registry import TaskRegistry  # noqa: E402

# Create a Celery instance. Default time zone is UTC.
app = Celery("celery")

# To register the custom tasks.
TaskRegistry()

# Use Redis as the message broker.
app.conf.broker_url = settings.CELERY_BROKER_URL
app.conf.result_backend = settings.CELERY_RESULT_BACKEND

# Load task modules from all registered Django app configs.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks in all installed apps.
app.autodiscover_tasks()

# Define the queues to purge when the Celery broker is restarted.
queues_to_purge = [ExecutionLogConstants.CELERY_QUEUE_NAME]
with app.connection() as connection:
    channel = connection.channel()

    for queue_name in queues_to_purge:
        channel.queue_purge(queue_name)

# Use the Django-Celery-Beat scheduler.
app.conf.beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"
