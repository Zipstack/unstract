from urllib.parse import quote_plus

from django.conf import settings
from kombu import Queue


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

    # Connection resilience settings
    broker_connection_retry_on_startup = True
    broker_connection_retry = True
    broker_connection_max_retries = 10

    # Broker transport options for resilience
    broker_transport_options = {
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 1,
        "socket_timeout": 30,
        "socket_keepalive": True,
    }

    # Worker configuration
    worker_prefetch_multiplier = 4
    worker_max_tasks_per_child = 1000

    # Queue definitions for different task types
    task_queues = [
        Queue("celery", routing_key="celery"),
        Queue("dashboard_metric_events", routing_key="dashboard_metric_events"),
        Queue("celery_periodic_logs", routing_key="celery_periodic_logs"),
        Queue("celery_log_task_queue", routing_key="celery_log_task_queue"),
        Queue("celery_api_deployments", routing_key="celery_api_deployments"),
        Queue("file_processing", routing_key="file_processing"),
        Queue("api_file_processing", routing_key="api_file_processing"),
        Queue("file_processing_callback", routing_key="file_processing_callback"),
        Queue("api_file_processing_callback", routing_key="api_file_processing_callback"),
    ]

    # Task routing for dashboard metrics
    task_routes = {
        "dashboard_metrics.process_events": {"queue": "dashboard_metric_events"},
        "dashboard_metrics.cleanup_hourly_data": {"queue": "dashboard_metric_events"},
        "dashboard_metrics.cleanup_daily_data": {"queue": "dashboard_metric_events"},
    }
