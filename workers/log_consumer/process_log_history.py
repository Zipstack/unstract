#!/usr/bin/env python3
"""Check log history queue and trigger backend processing.

This script:
1. Checks if logs exist in Redis queue (lightweight LLEN operation)
2. If logs exist, calls backend internal API to process them
3. Backend handles Redis LPOP, validation, and bulk DB insert

This avoids duplicating Redis/business logic in workers and minimizes API calls.

Usage:
    python process_log_history.py
"""

import logging
import os
import sys

import httpx
from unstract.core.cache.redis_queue_client import RedisQueueClient

logger = logging.getLogger(__name__)


def process_log_history():
    """Check if logs exist in queue and trigger backend processing."""
    try:
        # Backend API configuration
        internal_api_base_url = os.getenv("INTERNAL_API_BASE_URL")
        internal_api_key = os.getenv("INTERNAL_SERVICE_API_KEY")

        if not internal_api_base_url:
            logger.error("INTERNAL_API_BASE_URL environment variable not set")
            return False

        if not internal_api_key:
            logger.error("INTERNAL_SERVICE_API_KEY environment variable not set")
            return False

        # Connect to Redis using shared utility (only for checking queue length)
        log_queue_name = os.getenv("LOG_HISTORY_QUEUE_NAME")
        if not log_queue_name:
            logger.error("LOG_HISTORY_QUEUE_NAME environment variable not set")
            return False
        redis_client = RedisQueueClient.from_env()

        # Check if logs exist in queue (lightweight operation)
        queue_length = redis_client.llen(log_queue_name)

        if queue_length == 0:
            logger.info(f"No logs found in queue '{log_queue_name}'")
            return True

        logger.info(
            f"Found {queue_length} logs in queue '{log_queue_name}', "
            f"calling backend to process..."
        )

        # Call backend API to process logs (backend uses its own configured constants)
        # Use client with automatic retries for transient network failures
        transport = httpx.HTTPTransport(retries=3)
        with httpx.Client(transport=transport) as client:
            response = client.post(
                f"{internal_api_base_url.rstrip('/')}/v1/execution-logs/process-log-history/",
                headers={
                    "Authorization": f"Bearer {internal_api_key}",
                },
                timeout=30.0,
            )

        if response.status_code == 200:
            result = response.json()
            logger.info(
                f"Successfully processed {result.get('processed_count', 0)} logs "
                f"(skipped: {result.get('skipped_count', 0)})"
            )
            return True
        else:
            logger.error(
                f"Error: Backend returned status {response.status_code}: {response.text}"
            )
            return False

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling backend: {e}")
        return False
    except Exception:
        logger.exception("Unexpected error")
        return False


if __name__ == "__main__":
    success = process_log_history()
    sys.exit(0 if success else 1)
