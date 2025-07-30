from urllib.parse import quote_plus

from django.conf import settings

from backend.celery_backend_types import CeleryBackendTypes


def get_result_backend_url(backend_type):
    """Generate result backend URL based on backend type"""
    backend_type = backend_type.lower()
    
    if backend_type == CeleryBackendTypes.REDIS:
        # Redis backend configuration
        if settings.REDIS_PASSWORD:
            return f"redis://{settings.REDIS_USER}:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.CELERY_REDIS_DB}"
        else:
            return f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.CELERY_REDIS_DB}"
    else:
        # Default to PostgreSQL backend
        return (
            f"db+postgresql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )


class CeleryConfig:
    """Specifies celery configuration

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    # Result backend configuration - default from settings
    result_backend = get_result_backend_url(settings.CELERY_RESULT_BACKEND_TYPE)

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
