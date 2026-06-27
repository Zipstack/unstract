"""Task definitions for the task backend worker.

This module contains the actual task implementations that will be
registered with the backend abstraction layer.
"""

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
        "worker": "task-backend",
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


def add_numbers(a: int, b: int) -> int:
    """Simple arithmetic task for testing.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of the two numbers
    """
    logger.info(f"Executing add_numbers task: {a} + {b}")
    result = a + b
    logger.info(f"Add result: {result}")
    return result


def process_data(data: dict[str, Any], operation: str = "validate") -> dict[str, Any]:
    """Generic data processing task.

    Args:
        data: Input data to process
        operation: Type of operation to perform

    Returns:
        Processed data with metadata
    """
    logger.info(
        f"Executing process_data task - operation: {operation}, data_keys: {list(data.keys())}"
    )

    processed_data = {
        "original": data,
        "operation": operation,
        "processed_at": time.time(),
        "status": "completed",
    }

    # Simulate some processing based on operation
    if operation == "validate":
        processed_data["valid"] = isinstance(data, dict) and len(data) > 0
    elif operation == "transform":
        processed_data["transformed"] = {k: str(v).upper() for k, v in data.items()}
    elif operation == "count":
        processed_data["count"] = len(data)

    return processed_data


def simulate_work(duration: int = 1) -> dict[str, Any]:
    """Task that simulates some work by sleeping.

    Args:
        duration: How long to sleep in seconds

    Returns:
        Metadata about the work performed
    """
    logger.info(f"Executing simulate_work task for {duration} seconds")
    start_time = time.time()

    time.sleep(duration)

    end_time = time.time()
    actual_duration = end_time - start_time

    logger.info(f"Work simulation completed in {actual_duration:.2f} seconds")

    return {
        "requested_duration": duration,
        "actual_duration": actual_duration,
        "start_time": start_time,
        "end_time": end_time,
        "status": "completed",
    }


def concat_with_number(base_string: str, number: int) -> str:
    """Concatenate a string with a number.

    Args:
        base_string: The base string to concatenate
        number: The number to append

    Returns:
        Concatenated string with number
    """
    logger.info(f"Executing concat_with_number task: '{base_string}' + {number}")
    result = f"{base_string}{number}"
    logger.info(f"Concat result: {result}")
    return result


# List of all tasks that should be registered
TASK_REGISTRY = [
    health_check,
    echo,
    add_numbers,
    process_data,
    simulate_work,
    concat_with_number,
]
