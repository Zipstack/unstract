from urllib.parse import quote_plus

from django.conf import settings

from unstract.core.utilities import UnstractUtils


class CeleryConfig:
    """Specifies celery configuration

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    # Envs defined for configuration with Unstract
    CELERY_BROKER_URL = "CELERY_BROKER_URL"
    CELERY_BROKER_VISIBILITY_TIMEOUT = "CELERY_BROKER_VISIBILITY_TIMEOUT"

    # Result backend configuration
    result_backend = (
        f"db+postgresql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )

    # Broker URL configuration for RabbitMQ
    broker_url = UnstractUtils.get_env(
        CELERY_BROKER_URL,
        f"amqp://{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASS}@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}//",
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

    task_acks_late = True
