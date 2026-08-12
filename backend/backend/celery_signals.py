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
from celery.signals import before_task_publish, task_postrun, task_prerun
from log_request_id import local as log_request_id_local
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


def _request_id_from_task(task) -> str | None:
    """Read a propagated request_id off a Celery task's message context."""
    request = getattr(task, "request", None)
    if request is None:
        return None
    request_id = getattr(request, Common.REQUEST_ID, None)
    if not request_id:
        task_headers = getattr(request, "headers", None)
        if isinstance(task_headers, dict):
            request_id = task_headers.get(Common.REQUEST_ID)
    return request_id or None


@task_prerun.connect
def bind_request_id(task=None, **kwargs):
    """Bind the propagated request_id for tasks executed by the backend's OWN
    Celery workers (beat, dashboard-metric tasks, etc.).

    The separate ``workers/`` fleet has its own ``task_prerun`` reader; the
    backend Celery app previously injected the header (``propagate_request_id``)
    but never consumed it, so backend-executed tasks logged ``request_id:-``.
    Binding it onto ``log_request_id``'s thread-local makes
    ``log_request_id.filters.RequestIDFilter`` emit it, and onto ``StateStore``
    so any task this worker itself publishes re-propagates it.
    """
    request_id = _request_id_from_task(task)
    if not request_id:
        return
    log_request_id_local.request_id = request_id
    try:
        StateStore.set(Common.REQUEST_ID, request_id)
    except Exception:
        logger.debug("Unable to set request_id on StateStore", exc_info=True)


@task_postrun.connect
def clear_request_id(**kwargs):
    """Clear the task-scoped request_id bound in ``bind_request_id``."""
    if hasattr(log_request_id_local, "request_id"):
        try:
            del log_request_id_local.request_id
        except AttributeError:
            pass
    try:
        StateStore.clear(Common.REQUEST_ID)
    except Exception:
        logger.debug("Unable to clear request_id from StateStore", exc_info=True)
