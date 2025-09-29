"""Basic mathematical and string operations."""

import logging

logger = logging.getLogger(__name__)


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


def format_result_message(number: int) -> str:
    """Format a number into a result message (Celery chain-friendly).

    This task is designed for Celery chains where the previous result
    becomes the first argument automatically.

    Args:
        number: The number to format into a message

    Returns:
        Formatted result message
    """
    logger.info(f"Executing format_result_message task with number: {number}")
    result = f"Result is {number}"
    logger.info(f"Formatted message: {result}")
    return result


BASIC_OPERATION_TASKS = [
    add_numbers,
    concat_with_number,
    format_result_message,
]