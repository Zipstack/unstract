#!/usr/bin/env python3
"""Trigger backend processing of the notification buffer.

Mirrors process_log_history.py: a thin wrapper around an internal API call
that the log_consumer scheduler.sh fires on every tick. The backend owns the
actual GROUP BY / SKIP LOCKED / dispatch logic. Idempotent — safe to run
under multiple replicas (the backend's row-level lock prevents duplicate
dispatch).

Usage:
    python process_notification_buffer.py
"""

import logging
import os
import sys

import httpx

logger = logging.getLogger(__name__)

# Endpoint must match the URL registered in
# backend/notification_v2/internal_urls.py + backend/backend/internal_base_urls.py
PROCESS_BUFFER_ENDPOINT = "v1/webhook/buffer/process/"


def process_notification_buffer() -> bool:
    """Hit the backend's process-buffer endpoint; return True on success.

    Returns False on auth/network failure so the calling scheduler can log
    the failure and proceed to the next tick. Never raises — the scheduler
    is supposed to keep ticking.
    """
    internal_api_base_url = os.getenv("INTERNAL_API_BASE_URL")
    internal_api_key = os.getenv("INTERNAL_SERVICE_API_KEY")

    if not internal_api_base_url:
        logger.error("INTERNAL_API_BASE_URL environment variable not set")
        return False
    if not internal_api_key:
        logger.error("INTERNAL_SERVICE_API_KEY environment variable not set")
        return False

    url = f"{internal_api_base_url.rstrip('/')}/{PROCESS_BUFFER_ENDPOINT}"
    # Longer timeout than process_log_history (60s vs 30s): a flush tick can
    # involve multiple Celery dispatches, GC, and per-group rendering.
    transport = httpx.HTTPTransport(retries=3)
    try:
        with httpx.Client(transport=transport) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {internal_api_key}"},
                timeout=60.0,
            )
    except httpx.HTTPError:
        logger.exception("HTTP error calling process-buffer")
        return False
    except Exception:
        logger.exception("Unexpected error calling process-buffer")
        return False

    if response.status_code != 200:
        logger.error(
            "Backend returned status %s on process-buffer: %s",
            response.status_code,
            response.text[:500],
        )
        return False

    # A 200 with a non-JSON body (proxy/error page) would raise here; keep the
    # "never raises" contract so the scheduler keeps ticking.
    try:
        result = response.json()
    except ValueError:
        logger.error("Non-JSON 200 response from process-buffer: %s", response.text[:500])
        return False

    if result.get("dispatched_groups", 0) > 0 or result.get("gc_deleted_rows", 0) > 0:
        logger.info(
            "Notification buffer flush: groups=%s rows=%s reclaimed=%s gc=%s",
            result.get("dispatched_groups", 0),
            result.get("dispatched_rows", 0),
            result.get("reclaimed_rows", 0),
            result.get("gc_deleted_rows", 0),
        )
    return True


if __name__ == "__main__":
    success = process_notification_buffer()
    sys.exit(0 if success else 1)
