"""Queue backend for Dashboard Pipeline.

Sends metric events to RabbitMQ as Celery tasks for processing.
"""
import json
import logging
import time
import uuid
from typing import Any

from kombu import Connection, Exchange, Queue as KombuQueue
from kombu.exceptions import KombuError

from .base import AbstractMetricBackend
from ..types import MetricEvent

logger = logging.getLogger(__name__)

# Celery task name for processing metric events
CELERY_TASK_NAME = "dashboard_metrics.process_events"

# Default queue name for dashboard metric events
DEFAULT_QUEUE_NAME = "dashboard_metric_events"


class QueueBackend(AbstractMetricBackend):
    """Backend that sends metrics as Celery tasks to RabbitMQ.

    Events are sent as Celery task messages and processed by workers,
    then aggregated and stored in PostgreSQL.
    """

    def __init__(
        self,
        broker_url: str,
        queue_name: str = DEFAULT_QUEUE_NAME,
        task_name: str = CELERY_TASK_NAME,
    ) -> None:
        """Initialize the queue backend.

        Args:
            broker_url: RabbitMQ connection URL
            queue_name: Celery queue name (default: "dashboard_metric_events")
            task_name: Celery task name for processing events
        """
        self.broker_url = broker_url
        self.queue_name = queue_name
        self.task_name = task_name
        # Use Celery's default exchange
        self.exchange = Exchange("", type="direct")
        self.queue = KombuQueue(
            queue_name,
            self.exchange,
            routing_key=queue_name,
            durable=True,
        )
        self._connection: Connection | None = None
        self._max_retries = 3
        self._base_delay = 1.0

    def _get_connection(self) -> Connection:
        """Get or create a connection to the broker with retry logic."""
        if self._connection is not None and self._connection.connected:
            return self._connection
        return self._get_connection_with_retry()

    def _get_connection_with_retry(
        self,
        max_retries: int | None = None,
        base_delay: float | None = None,
    ) -> Connection:
        """Get connection with exponential backoff retry.

        Args:
            max_retries: Maximum retry attempts (default: 3)
            base_delay: Initial delay between retries in seconds (default: 1.0)

        Returns:
            Connected Connection object

        Raises:
            KombuError: If all retry attempts fail
        """
        retries = max_retries if max_retries is not None else self._max_retries
        delay = base_delay if base_delay is not None else self._base_delay

        last_error = None
        for attempt in range(retries):
            try:
                if self._connection is not None:
                    try:
                        self._connection.close()
                    except Exception:
                        pass

                self._connection = Connection(self.broker_url)
                self._connection.connect()
                logger.debug("Successfully connected to message broker")
                return self._connection

            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    sleep_time = delay * (2 ** attempt)
                    logger.warning(
                        f"Connection attempt {attempt + 1}/{retries} failed: {e}, "
                        f"retrying in {sleep_time:.1f}s"
                    )
                    time.sleep(sleep_time)
                else:
                    logger.error(
                        f"All {retries} connection attempts failed: {e}"
                    )

        raise KombuError(f"Failed to connect after {retries} attempts: {last_error}")

    def record(self, event: MetricEvent) -> bool:
        """Send a metric event as a Celery task.

        Args:
            event: The MetricEvent to queue

        Returns:
            True if the event was queued successfully, False otherwise
        """
        try:
            event_data = self._create_event_data(event)
            task_message = self._create_celery_message(event_data)
            conn = self._get_connection()

            with conn.Producer() as producer:
                producer.publish(
                    task_message,
                    exchange=self.exchange,
                    routing_key=self.queue_name,
                    declare=[self.queue],
                    delivery_mode=2,  # Persistent
                    content_type="application/json",
                    content_encoding="utf-8",
                    headers={
                        "task": self.task_name,
                        "id": str(uuid.uuid4()),
                    },
                )

            logger.debug(
                f"Queued metric task: {event.metric_name} for org {event.org_id}"
            )
            return True

        except KombuError as e:
            logger.error(f"Failed to queue metric {event.metric_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error queuing metric: {e}")
            return False

    def _create_event_data(self, event: MetricEvent) -> dict[str, Any]:
        """Create the event data payload.

        Args:
            event: The MetricEvent to serialize

        Returns:
            Dictionary with event data
        """
        return {
            "timestamp": time.time(),
            "org_id": event.org_id,
            "metric_name": event.metric_name,
            "metric_value": event.metric_value,
            "metric_type": event.metric_type.value,
            "labels": event.labels,
            "project": event.project,
            "tag": event.tag,
        }

    def _create_celery_message(self, event_data: dict[str, Any]) -> str:
        """Create a Celery-compatible task message.

        Args:
            event_data: The event data to include as task argument

        Returns:
            JSON-encoded Celery task message
        """
        # Celery message format (protocol v2)
        message = [
            [event_data],  # args - list of positional arguments
            {},            # kwargs - dict of keyword arguments
            {              # embed - task options
                "callbacks": None,
                "errbacks": None,
                "chain": None,
                "chord": None,
            },
        ]
        return json.dumps(message)

    def flush(self) -> None:
        """Flush is not needed for queue backend.

        Events are immediately sent to the queue.
        """
        pass

    def close(self) -> None:
        """Close the connection to the broker."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._connection = None
