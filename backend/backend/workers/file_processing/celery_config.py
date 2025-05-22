from kombu import Queue

from backend.celery_config import CeleryConfig as BaseCeleryConfig
from backend.workers.file_processing.constants import QueueNames


class CeleryConfig(BaseCeleryConfig):
    """Specifies celery configuration for file processing

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    task_queues = [
        Queue(QueueNames.FILE_PROCESSING, routing_key=QueueNames.FILE_PROCESSING),
        Queue(QueueNames.API_FILE_PROCESSING, routing_key=QueueNames.API_FILE_PROCESSING),
    ]

    task_default_queue = QueueNames.FILE_PROCESSING

    imports = ["workflow_manager.workflow_v2.file_execution_tasks"]
