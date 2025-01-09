class LogFieldName:
    EXECUTION_ID = "execution_id"
    ORGANIZATION_ID = "organization_id"
    TIMESTAMP = "timestamp"
    TYPE = "type"
    DATA = "data"
    EVENT_TIME = "event_time"
    FILE_EXECUTION_ID = "file_execution_id"


class LogEventArgument:
    EVENT = "event"
    MESSAGE = "message"
    USER_SESSION_ID = "user_session_id"


class LogProcessingTask:
    TASK_NAME = "logs_consumer"
    QUEUE_NAME = "celery_log_task_queue"
