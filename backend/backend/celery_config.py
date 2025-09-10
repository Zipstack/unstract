import logging
import os
from urllib.parse import quote_plus

from django.conf import settings

from backend.celery_db_retry import get_celery_db_engine_options, should_use_builtin_retry

logger = logging.getLogger(__name__)


class CeleryConfig:
    """Specifies celery configuration with hybrid retry support.

    Supports both custom retry (via patching) and Celery's built-in retry
    based on CELERY_USE_BUILTIN_RETRY environment variable.

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    # Result backend configuration
    result_backend = (
        f"db+postgresql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.CELERY_BACKEND_DB_NAME}"
    )

    # Broker URL configuration
    broker_url = settings.CELERY_BROKER_URL

    # Task serialization and content settings
    accept_content = ["json"]
    task_serializer = "json"
    result_serializer = "json"
    result_extended = True

    # Timezone and logger settings
    timezone = "UTC"
    worker_hijack_root_logger = False

    beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"

    task_acks_late = True

    # Database backend engine options for PgBouncer compatibility
    result_backend_transport_options = get_celery_db_engine_options()

    # Hybrid retry configuration - built-in vs custom
    if should_use_builtin_retry():
        # Use Celery's built-in database backend retry
        result_backend_always_retry = (
            os.environ.get("CELERY_RESULT_BACKEND_ALWAYS_RETRY", "true").lower() == "true"
        )
        result_backend_max_retries = int(
            os.environ.get("CELERY_RESULT_BACKEND_MAX_RETRIES", "3")
        )
        result_backend_base_sleep_between_retries_ms = int(
            os.environ.get("CELERY_RESULT_BACKEND_BASE_SLEEP_BETWEEN_RETRIES_MS", "1000")
        )
        result_backend_max_sleep_between_retries_ms = int(
            os.environ.get("CELERY_RESULT_BACKEND_MAX_SLEEP_BETWEEN_RETRIES_MS", "30000")
        )

        logger.info(
            f"[Celery Config] Using built-in retry: max_retries={result_backend_max_retries}, "
            f"base_sleep={result_backend_base_sleep_between_retries_ms}ms, max_sleep={result_backend_max_sleep_between_retries_ms}ms"
        )
    else:
        # Custom retry is handled by patch_celery_database_backend()
        logger.info("[Celery Config] Using custom retry system (patching enabled)")
