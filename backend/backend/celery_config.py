import os
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

    # Task routing configuration - Applied by default unless explicitly disabled
    # When ENABLE_WORKER_ROUTING=true (default), tasks are routed to specific queues
    # When ENABLE_WORKER_ROUTING=false, uses default Celery routing (backward compatibility)
    # To disable routing for old deployments, set ENABLE_WORKER_ROUTING=false
    if os.getenv("ENABLE_WORKER_ROUTING", "true").lower() == "true":
        # Task routing for distributed workers
        # These routes are only applied when running new worker architecture
        task_routes = {
            # Scheduler tasks - route to scheduler queue when scheduler worker is available
            "scheduler.tasks.execute_pipeline_task": {
                "queue": os.getenv("SCHEDULER_QUEUE", "scheduler")
            },
            # Notification tasks - route to notifications queue
            "send_webhook_notification": {
                "queue": os.getenv("NOTIFICATION_QUEUE", "notifications")
            },
            # File processing tasks - route to file_processing queue
            "process_file_batch": {
                "queue": os.getenv("FILE_PROCESSING_QUEUE", "file_processing")
            },
            "execute_single_file": {
                "queue": os.getenv("FILE_PROCESSING_QUEUE", "file_processing")
            },
            "update_file_execution_status": {
                "queue": os.getenv("FILE_PROCESSING_QUEUE", "file_processing")
            },
            # Callback tasks - route to callback queue
            "process_batch_callback": {"queue": os.getenv("CALLBACK_QUEUE", "callback")},
            "update_workflow_execution_status": {
                "queue": os.getenv("CALLBACK_QUEUE", "callback")
            },
            "update_pipeline_status": {"queue": os.getenv("CALLBACK_QUEUE", "callback")},
            # API deployment tasks - route to api_deployments queue
            "deploy_api_workflow": {
                "queue": os.getenv("API_DEPLOYMENT_QUEUE", "api_deployments")
            },
            "undeploy_api_workflow": {
                "queue": os.getenv("API_DEPLOYMENT_QUEUE", "api_deployments")
            },
            "check_api_deployment_status": {
                "queue": os.getenv("API_DEPLOYMENT_QUEUE", "api_deployments")
            },
            # General orchestration tasks - route to general queue
            "async_execute_bin_api": {"queue": os.getenv("GENERAL_QUEUE", "general")},
            "execute_workflow_with_files": {
                "queue": os.getenv("GENERAL_QUEUE", "general")
            },
            "_orchestrate_file_processing_general": {
                "queue": os.getenv("GENERAL_QUEUE", "general")
            },
        }
    else:
        # Default behavior: No task routing (backward compatible)
        # All tasks go to default queues as before
        task_routes = {}
