from kombu import Queue

from backend.celery_config import CeleryConfig as BaseCeleryConfig


class CeleryConfig(BaseCeleryConfig):
    """Specifies celery configuration for file processing

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    task_queues = [
        Queue("file_processing", routing_key="file_processing"),
    ]

    task_default_queue = "file_processing"

    imports = ["workflow_manager.workflow_v2.file_execution_tasks"]
