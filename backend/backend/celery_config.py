from urllib.parse import quote_plus

from django.conf import settings


class CeleryConfig:
    """Specifies celery configuration

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

    # Route long-running Prompt Studio IDE tasks to a dedicated queue
    # so they don't compete with beat/logging/API-deployment tasks.
    task_routes = {
        "prompt_studio_index_document": {"queue": "celery_prompt_studio"},
        "prompt_studio_fetch_response": {"queue": "celery_prompt_studio"},
        "prompt_studio_single_pass": {"queue": "celery_prompt_studio"},
    }
