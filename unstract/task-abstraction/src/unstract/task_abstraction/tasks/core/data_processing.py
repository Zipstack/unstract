"""Data processing and transformation tasks."""

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


def process_data(data: Dict[str, Any], operation: str = "validate") -> Dict[str, Any]:
    """Generic data processing task.

    Args:
        data: Input data to process
        operation: Type of operation to perform

    Returns:
        Processed data with metadata
    """
    logger.info(f"Executing process_data task - operation: {operation}, data_keys: {list(data.keys())}")

    processed_data = {
        "original": data,
        "operation": operation,
        "processed_at": time.time(),
        "status": "completed"
    }

    # Simulate some processing based on operation
    if operation == "validate":
        processed_data["valid"] = isinstance(data, dict) and len(data) > 0
    elif operation == "transform":
        processed_data["transformed"] = {k: str(v).upper() for k, v in data.items()}
    elif operation == "count":
        processed_data["count"] = len(data)

    return processed_data


DATA_PROCESSING_TASKS = [
    process_data,
]