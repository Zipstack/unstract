from kombu import Queue

from backend.celery_config import CeleryConfig as BaseCeleryConfig
from backend.workers.file_processing_callback.constants import QueueNames


class CeleryConfig(BaseCeleryConfig):
    """Specifies celery configuration for file processing callback

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    task_queues = [
        Queue(
            QueueNames.FILE_PROCESSING_CALLBACK,
            routing_key=QueueNames.FILE_PROCESSING_CALLBACK,
        ),
        Queue(
            QueueNames.API_FILE_PROCESSING_CALLBACK,
            routing_key=QueueNames.API_FILE_PROCESSING_CALLBACK,
        ),
    ]

    task_default_queue = QueueNames.FILE_PROCESSING_CALLBACK
    # Prevents chord loss during scaling events
    worker_pool_restarts = True
    broker_connection_retry_on_startup = True

    # Chord-specific settings
    result_chord_retry_interval = 3  # Backend check interval in seconds

    imports = ["workflow_manager.workflow_v2.file_execution_tasks"]
