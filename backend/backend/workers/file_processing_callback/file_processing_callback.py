"""This module contains the Celery configuration for the backend project."""

import logging
import logging.config
import os
from pprint import pformat

from celery import Celery

from backend.settings.base import LOGGING
from backend.workers.constants import CeleryWorkerNames
from backend.workers.file_processing_callback.celery_config import CeleryConfig

logger = logging.getLogger(__name__)

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)

# Configure logging for celery worker using same config as Django
logging.config.dictConfig(LOGGING)

# Create a Celery instance. Default time zone is UTC.
app = Celery(CeleryWorkerNames.FILE_PROCESSING_CALLBACK)

# Load task modules from all registered Django app configs.
app.config_from_object(CeleryConfig)

logger.debug(f"Celery Configuration:\n {pformat(app.conf.table(with_defaults=True))}")
