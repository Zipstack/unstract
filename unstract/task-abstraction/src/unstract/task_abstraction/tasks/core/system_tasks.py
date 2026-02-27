"""System monitoring and utility tasks."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def health_check() -> dict[str, Any]:
    """Simple health check task that returns worker status.

    Returns:
        Dict containing health status and metadata
    """
    logger.info("Executing health_check task")
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "worker": "task-abstraction",
        "message": "Worker is operational",
    }


def echo(message: str) -> str:
    """Echo task that returns the input message.

    Args:
        message: The message to echo back

    Returns:
        The echoed message with prefix
    """
    logger.info(f"Executing echo task with message: {message}")
    return f"Echo: {message}"


def simulate_work(duration: int = 1) -> dict[str, Any]:
    """Task that simulates some work by sleeping.

    Args:
        duration: How long to sleep in seconds

    Returns:
        Metadata about the work performed
    """
    logger.info(f"Executing simulate_work task for {duration} seconds")
    start_time = time.perf_counter()

    time.sleep(duration)

    end_time = time.perf_counter()
    actual_duration = end_time - start_time

    logger.info(f"Work simulation completed in {actual_duration:.2f} seconds")

    return {
        "requested_duration": duration,
        "actual_duration": actual_duration,
        "start_time": start_time,
        "end_time": end_time,
        "status": "completed",
    }


SYSTEM_TASKS = [
    health_check,
    echo,
    simulate_work,
]
