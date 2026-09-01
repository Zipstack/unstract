import json
import logging
import os
import time
import traceback
from datetime import UTC, datetime
from typing import Any

import httpx
from kombu import Connection

from unstract.core.cache.redis_client import create_redis_client
from unstract.core.constants import LogEventArgument, LogProcessingTask

#: Transport for the log-streaming hop between this publisher and the log consumer.
#: ``celery`` (default) publishes a Celery-protocol message to RabbitMQ; ``redis``
#: RPUSHes onto a Redis list drained by the PG-era log consumer.
#:
#: Deliberately an env var rather than the ``pg_queue_enabled`` Flipt flag. The flag
#: routes *per execution*, which is meaningless here: the consumer is a single
#: deployment reading from exactly one place, so a per-org split would strand half the
#: logs in a queue nobody drains. Producer and consumer must agree cluster-wide, which
#: makes this deployment config. It must be flipped in step with the flag rollout.
_LOG_TRANSPORT_ENV = "LOG_TRANSPORT"
_LOG_TRANSPORT_REDIS = "redis"

#: Redis list used when ``LOG_TRANSPORT=redis``. Distinct from ``log_history_queue``,
#: which is the *downstream* durable buffer the consumer writes to — this one is the
#: transport itself, and is normally near-empty.
_LOG_STREAM_QUEUE_ENV = "LOG_STREAM_QUEUE_NAME"
_LOG_STREAM_QUEUE_DEFAULT = "log_stream_queue"

#: Cap mirroring ``store_execution_log``'s (unstract/core/log_utils.py): without it a
#: stopped consumer grows this list until Redis OOMs, which would take down far more
#: than logging. Dropping is the correct behaviour for this payload — logs are already
#: best-effort and are discarded at the same cap one hop downstream.
_LOG_STREAM_MAX_SIZE_ENV = "LOG_STREAM_QUEUE_MAX_SIZE"
_LOG_STREAM_MAX_SIZE_DEFAULT = 10000


def _use_redis_log_transport() -> bool:
    return os.getenv(_LOG_TRANSPORT_ENV, "celery").strip().lower() == _LOG_TRANSPORT_REDIS


class LogPublisher:
    broker_url = str(
        httpx.URL(os.getenv("CELERY_BROKER_BASE_URL", "amqp://")).copy_with(
            username=os.getenv("CELERY_BROKER_USER") or None,
            password=os.getenv("CELERY_BROKER_PASS") or None,
        )
    )
    kombu_conn = Connection(broker_url)
    _redis_client: Any = None

    @classmethod
    def _get_redis_client(cls) -> Any:
        if cls._redis_client is None:
            cls._redis_client = create_redis_client(decode_responses=False)
        return cls._redis_client

    @staticmethod
    def log_usage(
        level: str = "INFO",
        added_token_count: int | None = None,
        max_token_count_set: int | None = None,
        enabled: bool = False,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(UTC).timestamp(),
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
        cost_type: str | None = None,
        cost_units: str | None = None,
        cost_value: float | None = None,
        step: int | None = None,
        iteration: int | None = None,
        iteration_total: int | None = None,
        execution_id: str | None = None,
        file_execution_id: str | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(UTC).timestamp(),
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
        component: str | None,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(UTC).timestamp(),
            "type": "UPDATE",
            "component": component,
            "state": state,
            "message": message,
        }

    @staticmethod
    def log_progress(
        component: dict[str, str],
        level: str,
        state: str,
        message: str,
    ) -> dict[str, str]:
        """Build a progress log message for streaming to the frontend.

        Same structure as ``log_prompt()`` but uses ``type: "PROGRESS"``
        so the frontend can distinguish executor progress from regular
        log messages.
        """
        return {
            "timestamp": datetime.now(UTC).timestamp(),
            "type": "PROGRESS",
            "service": "prompt",
            "component": component,
            "level": level,
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
            "timestamp": datetime.now(UTC).timestamp(),
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
            task_message = cls._get_task_message(
                user_session_id=channel_id,
                event=event,
                message=payload,
            )
            if _use_redis_log_transport():
                cls._publish_via_redis(task_message)
            else:
                with cls.kombu_conn.Producer(serializer="json") as producer:
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
    def _publish_via_redis(cls, task_message: dict[str, Any]) -> None:
        """RPUSH the log envelope onto the Redis transport list.

        The envelope carries the task name alongside the kwargs so the consumer
        dispatches by name exactly as the Celery header did — a bare kwargs blob would
        leave the consumer guessing, and a name mismatch is the silent failure mode
        (message read, no handler, dropped with nothing at the publish site to trace).

        Raises on Redis failure; ``publish()`` owns the swallow, so a logging fault can
        never break an execution.
        """
        queue_name = os.getenv(_LOG_STREAM_QUEUE_ENV, _LOG_STREAM_QUEUE_DEFAULT)
        max_size = int(
            os.getenv(_LOG_STREAM_MAX_SIZE_ENV, str(_LOG_STREAM_MAX_SIZE_DEFAULT))
        )
        redis_client = cls._get_redis_client()

        # O(1), and the same llen-then-push shape store_execution_log already uses one
        # hop downstream. Two Redis round trips per log line is the price of not letting
        # a stopped consumer OOM Redis.
        if redis_client.llen(queue_name) >= max_size:
            logging.warning(
                f"Log stream queue '{queue_name}' at capacity ({max_size}), "
                "dropping current log - log consumer may be down or falling behind"
            )
            return

        envelope = json.dumps(
            {
                "task": LogProcessingTask.TASK_NAME,
                "kwargs": task_message["kwargs"],
            }
        )
        redis_client.rpush(queue_name, envelope)

    @classmethod
    def store_for_unified_notification(cls, event: str, payload: dict[str, Any]) -> None:
        """Helps persist messages for unified notification.

        Message is stored in redis with a configurable TTL.
        Will be used to display such messages in the UI.

        Args:
            event (str): User session ID
            payload (dict[str, Any]): Message being sent
        """
        try:
            logs_expiration = os.environ.get(
                "LOGS_EXPIRATION_TIME_IN_SECOND", "3600"
            )  # Defaults to 1 hour
            timestamp = payload.get("timestamp", round(time.time(), 6))
            redis_key = f"{event}:{timestamp}"
            log_data = json.dumps(payload)
            cls._get_redis_client().setex(redis_key, logs_expiration, log_data)
        except Exception as e:
            logging.error(
                f"Failed to store unified notification log for '{event}' "
                f"<= {payload}: {e}\n{traceback.format_exc()}"
            )
