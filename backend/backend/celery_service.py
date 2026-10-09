"""This module contains the Celery configuration for the backend project."""

import logging
import logging.config
import os
from pprint import pformat

from celery import Celery
from celery.signals import task_postrun

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

# Load task modules from all registered Django app configs.
app.config_from_object("backend.celery_config.CeleryConfig")
app.autodiscover_tasks()

logger.debug(f"Celery Configuration:\n {pformat(app.conf.table(with_defaults=True))}")


@task_postrun.connect
def _drop_cached_organization(**kwargs: object) -> None:
    """Backstop for tasks that set the organization id and never clear it.

    Setting the id already drops the cached organization, so this only keeps a
    pool thread from carrying it into a task that relies on a leftover id.
    """
    # Lazy: account_v2.models needs the app registry, ready once tasks run.
    from utils.user_context import UserContext

    UserContext.clear_organization_cache()
