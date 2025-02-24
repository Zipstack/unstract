from urllib.parse import quote_plus

from django.conf import settings

from unstract.core.utilities import UnstractUtils


class CeleryConfig:
    """Specifies celery configuration

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    # Result backend configuration
    result_backend = (
        f"db+postgresql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )

    # Broker URL configuration
    broker_url = UnstractUtils.get_env(
        "CELERY_BROKER_URL",
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
        raise_err=True,
    )

    # Task serialization and content settings
    accept_content = ["json"]
    task_serializer = "json"
    result_serializer = "json"
    result_extended = True

    # Timezone and logger settings
    timezone = "UTC"
    worker_hijack_root_logger = False

    beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"

    # Large timeout avoids worker to pick up same unacknowledged task again
    broker_transport_options = {"visibility_timeout": 7200}  # 2 hours
