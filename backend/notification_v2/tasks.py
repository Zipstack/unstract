"""Celery tasks owned by notification_v2.

Currently hosts ``mark_buffer_dead_letter`` — a thin task attached as a
Celery ``link_error`` to the clubbed dispatch chain. When the underlying
``send_webhook_notification`` task exhausts retries, this task converts
the buffered rows from PENDING/DISPATCHED to terminal DEAD_LETTER so the
flush job will not re-pick them.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from backend.celery_service import app as celery_app
from notification_v2.enums import BufferStatus
from notification_v2.models import NotificationBuffer

logger = logging.getLogger(__name__)


@celery_app.task(name="notification_v2.mark_buffer_dead_letter")
def mark_buffer_dead_letter(
    request: Any,
    exc: Any = None,
    traceback: Any = None,
    *,
    buffer_row_ids: Iterable[str] | None = None,
) -> int:
    """Mark a clubbed dispatch's rows as DEAD_LETTER on terminal failure.

    Celery's ``link_error`` signature passes ``(request, exc, traceback)`` to
    the callback; the actual buffer ids are bound at dispatch time via task
    kwargs. Returns the row count for visibility in flower.
    """
    if not buffer_row_ids:
        logger.warning(
            "mark_buffer_dead_letter invoked without buffer_row_ids — nothing to do"
        )
        return 0
    ids = list(buffer_row_ids)
    updated: int = NotificationBuffer.objects.filter(id__in=ids).update(
        status=BufferStatus.DEAD_LETTER.value
    )
    logger.warning(
        "metric=notification_batch_dispatched_total result=dead_letter rows=%d " "exc=%r",
        updated,
        exc,
    )
    return updated
