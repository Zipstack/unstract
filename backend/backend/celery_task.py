import logging
import os
from typing import Any

from celery import shared_task
from utils.log_events import handle_user_logs

from unstract.core.constants import LogEventArgument, LogProcessingTask

logger = logging.getLogger(__name__)


class TaskRegistry:
    @staticmethod
    @shared_task(
        name=LogProcessingTask.TASK_NAME,
    )
    def log_consumer(**kwargs: Any) -> None:
        log_message = kwargs.get(LogEventArgument.MESSAGE)
        room = kwargs.get(LogEventArgument.USER_SESSION_ID)
        event = kwargs.get(LogEventArgument.EVENT)
        logger.debug(
            f"[{os.getpid()}] Log message received: {log_message} for the room {room}"
        )
        handle_user_logs(room=room, event=event, message=log_message)
