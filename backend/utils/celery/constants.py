from django.conf import settings
from utils.common_utils import CommonUtils


class ExecutionLogConstants:
    """Constants for ExecutionLog.

    Attributes:
        IS_ENABLED (bool): Whether to enable log history.
        LOGS_BATCH_LIMIT (str): The maximum number of logs to store in a batch.
        LOG_QUEUE_NAME (str): The name of the queue to store log history.
        CELERY_QUEUE_NAME (str): The name of the Celery queue to schedule log
            history consumers.
    """

    IS_ENABLED: bool = CommonUtils.str_to_bool(settings.ENABLE_LOG_HISTORY)
    LOGS_BATCH_LIMIT: int = settings.LOGS_BATCH_LIMIT
    LOG_QUEUE_NAME: str = "log_history_queue"
    CELERY_QUEUE_NAME = "celery_periodic_logs"
