"""Task definitions for the task abstraction library.

This module contains task implementations that can be used across
different backends (Celery, Hatchet, Temporal).
"""

from .core import CORE_TASKS

# Try to import enterprise tasks (folder may not exist in community builds)
try:
    from .enterprise import ENTERPRISE_TASKS
except ImportError:
    # Enterprise tasks folder doesn't exist (community build)
    ENTERPRISE_TASKS = []


def get_available_tasks():
    """Get all available tasks based on installation.

    Returns:
        List of task functions available for registration
    """
    tasks = CORE_TASKS.copy()
    tasks.extend(ENTERPRISE_TASKS)
    return tasks


# Default task registry
TASK_REGISTRY = get_available_tasks()

__all__ = ["TASK_REGISTRY"]
