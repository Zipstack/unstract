"""Error utility functions for user-friendly error messages."""

from celery.exceptions import SoftTimeLimitExceeded


def get_user_friendly_error_message(exception: Exception) -> str:
    """Convert exception to user-friendly error message.

    Currently handles SoftTimeLimitExceeded specifically.
    Other exceptions are passed through unchanged.

    Args:
        exception: The exception to convert.

    Returns:
        A user-friendly error message string.
    """
    if isinstance(exception, SoftTimeLimitExceeded):
        return "Processing timed out. Couldn't complete processing within the time limit."

    return str(exception)
