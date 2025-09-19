"""Shared log processing utilities for Unstract platform.

This module contains log processing utilities that can be used by both
backend Django services and worker processes for consistent log handling.
"""

import json
import logging
from typing import Any

import redis

from unstract.core.constants import LogFieldName
from unstract.core.data_models import LogDataDTO
from unstract.workflow_execution.enums import LogType

logger = logging.getLogger(__name__)


def get_validated_log_data(json_data: Any) -> LogDataDTO | None:
    """Validate log data to persist history.

    This function takes log data in JSON format, validates it, and returns a
    LogDataDTO object if the data is valid. The validation process includes
    decoding bytes to string, parsing the string as JSON, and checking for
    required fields and log type.

    Args:
        json_data (Any): Log data in JSON format

    Returns:
        LogDataDTO | None: Log data DTO object if valid, None otherwise
    """
    if isinstance(json_data, bytes):
        json_data = json_data.decode("utf-8")

    if isinstance(json_data, str):
        try:
            # Parse the string as JSON
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON data while validating {json_data}")
            return None

    if not isinstance(json_data, dict):
        logger.warning(f"Getting invalid data type while validating {json_data}")
        return None

    # Extract required fields from the JSON data
    execution_id = json_data.get(LogFieldName.EXECUTION_ID)
    organization_id = json_data.get(LogFieldName.ORGANIZATION_ID)
    timestamp = json_data.get(LogFieldName.TIMESTAMP)
    log_type = json_data.get(LogFieldName.TYPE)
    file_execution_id = json_data.get(LogFieldName.FILE_EXECUTION_ID)

    # Ensure the log type is LogType.LOG
    if log_type != LogType.LOG.value:
        return None

    # Check if all required fields are present
    if not all((execution_id, organization_id, timestamp)):
        logger.debug(f"Missing required fields while validating {json_data}")
        return None

    return LogDataDTO(
        execution_id=execution_id,
        file_execution_id=file_execution_id,
        organization_id=organization_id,
        timestamp=timestamp,
        log_type=log_type,
        data=json_data,
    )


def store_execution_log(
    data: dict[str, Any],
    redis_client: redis.Redis,
    log_queue_name: str,
    is_enabled: bool = True,
) -> None:
    """Store execution log in Redis queue.

    Args:
        data: Execution log data
        redis_client: Redis client instance
        log_queue_name: Name of the Redis queue to store logs
        is_enabled: Whether log storage is enabled
    """
    if not is_enabled:
        return

    try:
        log_data = get_validated_log_data(json_data=data)
        if log_data:
            redis_client.rpush(log_queue_name, log_data.to_json())
    except Exception as e:
        logger.error(f"Error storing execution log: {e}")


def create_redis_client(
    host: str = "localhost",
    port: int = 6379,
    username: str | None = None,
    password: str | None = None,
    **kwargs,
) -> redis.Redis:
    """Create Redis client with configuration.

    Args:
        host: Redis host
        port: Redis port
        username: Redis username (optional)
        password: Redis password (optional)
        **kwargs: Additional Redis configuration

    Returns:
        Configured Redis client
    """
    return redis.Redis(
        host=host,
        port=port,
        username=username,
        password=password,
        decode_responses=False,  # Keep as bytes for consistency
        **kwargs,
    )
