import json
import logging
import os
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import redis
from kombu import Connection

from unstract.core.constants import LogEventArgument, LogProcessingTask


class LogPublisher:
    kombu_conn = Connection(os.environ.get("CELERY_BROKER_URL"))
    r = redis.Redis(
        host=os.environ.get("REDIS_HOST"),
        port=os.environ.get("REDIS_PORT"),
        username=os.environ.get("REDIS_USER"),
        password=os.environ.get("REDIS_PASSWORD"),
    )

    @staticmethod
    def log_usage(
        level: str = "INFO",
        added_token_count: Optional[int] = None,
        max_token_count_set: Optional[int] = None,
        enabled: bool = False,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "LOG",
            "service": "usage",
            "level": level,
            "added_token_count": added_token_count,
            "max_token_count_set": max_token_count_set,
            "enabled": enabled,
        }

    @staticmethod
    def log_workflow(
        stage: str,
        message: str,
        level: str = "INFO",
        cost_type: Optional[str] = None,
        cost_units: Optional[str] = None,
        cost_value: Optional[float] = None,
        step: Optional[int] = None,
        iteration: Optional[int] = None,
        iteration_total: Optional[int] = None,
        execution_id: Optional[str] = None,
        file_execution_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "LOG",
            "level": level,
            "stage": stage,
            "log": message,
            "cost_type": cost_type,
            "cost_units": cost_units,
            "cost_value": cost_value,
            "step": step,
            "iteration": iteration,
            "iteration_total": iteration_total,
            "execution_id": execution_id,
            "file_execution_id": file_execution_id,
            "organization_id": organization_id,
        }

    @staticmethod
    def log_workflow_update(
        state: str,
        message: str,
        component: Optional[str],
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "UPDATE",
            "component": component,
            "state": state,
            "message": message,
        }

    @staticmethod
    def log_prompt(
        component: dict[str, str],
        level: str,
        state: str,
        message: str,
    ) -> dict[str, str]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "LOG",
            "service": "prompt",
            "component": component,
            "level": level,
            "state": state,
            "message": message,
        }

    @classmethod
    def _get_task_message(
        cls, user_session_id: str, event: str, message: Any
    ) -> dict[str, Any]:

        task_kwargs = {
            LogEventArgument.EVENT: event,
            LogEventArgument.MESSAGE: message,
            LogEventArgument.USER_SESSION_ID: user_session_id,
        }
        task_message = {
            "args": [],
            "kwargs": task_kwargs,
            "retries": 0,
            "utc": True,
        }
        return task_message

    @classmethod
    def _get_task_header(cls, task_name: str) -> dict[str, Any]:
        return {
            "task": task_name,
        }

    @classmethod
    def publish(cls, channel_id: str, payload: dict[str, Any]) -> bool:
        """Publish a message to the queue."""
        try:
            event = f"logs:{channel_id}"
            with cls.kombu_conn.Producer(serializer="json") as producer:
                task_message = cls._get_task_message(
                    user_session_id=channel_id,
                    event=event,
                    message=payload,
                )
                headers = cls._get_task_header(LogProcessingTask.TASK_NAME)
                # Publish the message to the queue
                producer.publish(
                    body=task_message,
                    exchange="",
                    headers=headers,
                    routing_key=LogProcessingTask.QUEUE_NAME,
                    compression=None,
                    retry=True,
                )
                logging.debug(f"Published '{channel_id}' <= {payload}")

                # Persisting messages for unified notification
                if payload.get("type") == "LOG":
                    cls.store_for_unified_notification(event, payload)
        except Exception as e:
            logging.error(
                f"Failed to publish '{channel_id}' <= {payload}"
                f": {e}\n{traceback.format_exc()}"
            )
            return False
        return True

    @classmethod
    def store_for_unified_notification(
        cls, event: str, payload: dict[str, Any]
    ) -> None:
        """Helps persist messages for unified notification.

        Message is stored in redis with a configurable TTL.
        Will be used to display such messages in the UI.

        Args:
            event (str): User session ID
            payload (dict[str, Any]): Message being sent
        """
        try:
            logs_expiration = os.environ.get(
                "LOGS_EXPIRATION_TIME_IN_SECOND", "86400"
            )  # Defaults to 1 day
            timestamp = payload.get("timestamp", round(time.time(), 6))
            redis_key = f"{event}:{timestamp}"
            log_data = json.dumps(payload)
            cls.r.setex(redis_key, logs_expiration, log_data)
        except Exception as e:
            logging.error(
                f"Failed to store unified notification log for '{event}' "
                f"<= {payload}: {e}\n{traceback.format_exc()}"
            )
