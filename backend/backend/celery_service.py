"""This module contains the Celery configuration for the backend project."""

import logging
import logging.config
import os
from pprint import pformat

from celery import Celery

from backend.celery_db_retry import patch_celery_database_backend
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

# Patch Celery database backend to add connection retry logic
patch_celery_database_backend()

# Register custom tasks
TaskRegistry()

# Load task modules from all registered Django app configs.
app.config_from_object("backend.celery_config.CeleryConfig")
app.autodiscover_tasks()

logger.debug(f"Celery Configuration:\n {pformat(app.conf.table(with_defaults=True))}")
