"""Notification Worker Utilities

Worker-specific utility functions for notification processing.
"""

import logging
from typing import Any

from shared.logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


def log_notification_attempt(
    notification_type: str,
    destination: str,
    attempt: int,
    max_attempts: int | None = None,
) -> None:
    """Log notification attempt.

    Args:
        notification_type: Type of notification
        destination: Target destination
        attempt: Current attempt number
        max_attempts: Maximum number of attempts
    """
    attempt_info = f"attempt {attempt}"
    if max_attempts:
        attempt_info += f"/{max_attempts}"

    logger.info(
        f"Sending {notification_type} notification to {destination} ({attempt_info})"
    )


def log_notification_success(
    notification_type: str,
    destination: str,
    attempt: int,
    response_info: dict[str, Any] | None = None,
) -> None:
    """Log successful notification delivery.

    Args:
        notification_type: Type of notification
        destination: Target destination
        attempt: Number of attempts taken
        response_info: Additional response information
    """
    success_msg = f"{notification_type} notification sent successfully to {destination}"
    if attempt > 1:
        success_msg += f" (after {attempt} attempts)"

    if response_info and response_info.get("status_code"):
        success_msg += f" (status: {response_info['status_code']})"

    logger.info(success_msg)


def log_notification_failure(
    notification_type: str,
    destination: str,
    error: Exception,
    attempt: int,
    is_final: bool = False,
) -> None:
    """Log notification failure.

    Args:
        notification_type: Type of notification
        destination: Target destination
        error: Exception that occurred
        attempt: Current attempt number
        is_final: Whether this is the final attempt
    """
    level = logging.ERROR if is_final else logging.WARNING

    failure_msg = f"{notification_type} notification failed to {destination} (attempt {attempt}): {str(error)}"
    if is_final:
        failure_msg = f"Final failure - {failure_msg}"

    logger.log(level, failure_msg)
