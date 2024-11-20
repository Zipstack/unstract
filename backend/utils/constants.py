import os

from django.conf import settings
from utils.common_utils import CommonUtils

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)


class Account:
    CREATED_BY = "created_by"
    MODIFIED_BY = "modified_by"
    ORGANIZATION_ID = "organization_id"


class FeatureFlag:
    """Temporary feature flags."""

    REMOTE_FILE_STORAGE = "remote_file_storage"

    pass


class Common:
    METADATA = "metadata"
    MODULE = "module"
    CONNECTOR = "connector"


class Pagination:
    """Constants for Pagination.

    Attributes:
        PAGE_SIZE (int): The default number of items per page.
        PAGE_SIZE_QUERY_PARAM (str): The name of the query parameter used to
            specify page size in requests. Ex: ?page=2&<PAGE_SIZE_QUERY_PARAM>=3
        MAX_PAGE_SIZE (int): The maximum allowed number of items per page.
    """

    PAGE_SIZE = 50
    PAGE_SIZE_QUERY_PARAM = "page_size"
    MAX_PAGE_SIZE = 1000


class CeleryQueue:
    """Constants for Celery Queue.

    Attributes:
        CELERY_API_DEPLOYMENTS (str): The name of the Celery queue for API
            deployments.
    """

    CELERY_API_DEPLOYMENTS = "celery_api_deployments"


class ExecutionLogConstants:
    """Constants for ExecutionLog.

    Attributes:
        IS_ENABLED (bool): Whether to enable log history.
        CONSUMER_INTERVAL (int): The interval (in seconds) between log history
            consumers.
        LOG_QUEUE_NAME (str): The name of the queue to store log history.
        LOGS_BATCH_LIMIT (str): The maximum number of logs to store in a batch.
        CELERY_QUEUE_NAME (str): The name of the Celery queue to schedule log
            history consumers.
        PERIODIC_TASK_NAME (str): The name of the Celery periodic task to schedule
            log history consumers.
        TASK (str): The name of the Celery task to schedule log history consumers.
    """

    IS_ENABLED: bool = CommonUtils.str_to_bool(settings.ENABLE_LOG_HISTORY)
    CONSUMER_INTERVAL: int = settings.LOG_HISTORY_CONSUMER_INTERVAL
    LOGS_BATCH_LIMIT: int = settings.LOGS_BATCH_LIMIT
    LOG_QUEUE_NAME: str = "log_history_queue"
    CELERY_QUEUE_NAME = "celery_periodic_logs"
    PERIODIC_TASK_NAME = "workflow_log_history"
    PERIODIC_TASK_NAME_V2 = "workflow_log_history_v2"
    TASK = "workflow_manager.workflow.execution_log_utils.consume_log_history"
    TASK_V2 = "consume_log_history"
