"""Celery signal handlers for the backend (producer side).

Propagates the HTTP ``request_id`` (correlation ID assigned by
``CustomRequestIDMiddleware``) onto every published Celery task so that worker
logs can be correlated back to the originating request.

The value is placed in the task message headers under ``request_id``. Workers
read it from ``task.request`` in ``task_prerun`` and bind it onto their log
context -- see ``workers/shared/infrastructure/logging/logger.py``. Using the
``before_task_publish`` signal means this works for *every* ``send_task`` /
``.delay`` / ``.apply_async`` call with no per-call-site changes.
"""

import logging

from account_v2.constants import Common
from celery.signals import before_task_publish
from utils.local_context import StateStore

logger = logging.getLogger(__name__)


@before_task_publish.connect
def propagate_request_id(headers=None, **kwargs):
    """Inject the current request_id into the outgoing task's message headers.

    Fires in the producer thread (the web request thread for API-triggered
    tasks), where ``StateStore`` still holds the request_id set by
    ``CustomRequestIDMiddleware``. No-ops when there is no request_id in scope
    (e.g. beat-scheduled publishes), leaving the worker to fall back to its
    own correlation id (execution_id / task_id).
    """
    if headers is None:
        return
    try:
        request_id = StateStore.get(Common.REQUEST_ID)
    except Exception:
        # StateStore can raise if CONCURRENCY_MODE is misconfigured; never let
        # correlation plumbing break task publishing.
        logger.debug("Unable to read request_id from StateStore", exc_info=True)
        return
    if request_id and not headers.get(Common.REQUEST_ID):
        headers[Common.REQUEST_ID] = request_id
