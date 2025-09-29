"""Core task modules available in all editions."""

from .basic_operations import BASIC_OPERATION_TASKS
from .system_tasks import SYSTEM_TASKS
from .data_processing import DATA_PROCESSING_TASKS

# Combine all core tasks
CORE_TASKS = []
CORE_TASKS.extend(BASIC_OPERATION_TASKS)
CORE_TASKS.extend(SYSTEM_TASKS)
CORE_TASKS.extend(DATA_PROCESSING_TASKS)

__all__ = ["CORE_TASKS"]