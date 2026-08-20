"""Celery signal handlers carrying the HTTP ``request_id`` onto published tasks.

The id travels in the task message headers under ``Common.REQUEST_ID``. Hooking
``before_task_publish`` rather than each producer is deliberate: it covers every
``send_task`` / ``.delay`` / ``.apply_async`` with no per-call-site change.
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

    Relies on firing in the *producer* thread, where ``StateStore`` still holds
    the id set by ``CustomRequestIDMiddleware``. No-ops without one (e.g. beat
    publishes), leaving the worker to derive its own correlation id.
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
    """Bind the propagated request_id for tasks run by the backend's own workers.

    Two writes, both required: ``log_request_id``'s thread-local is the only
    thing ``log_request_id.filters.RequestIDFilter`` reads (the HTTP middleware
    is otherwise its sole writer, so a task would log ``request_id:-``), and
    ``StateStore`` is what ``propagate_request_id`` reads, so tasks this worker
    itself publishes carry the id onward.
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
    """Clear the task-scoped request_id -- worker threads are pooled and reused."""
    if hasattr(log_request_id_local, "request_id"):
        try:
            del log_request_id_local.request_id
        except AttributeError:
            pass
    try:
        StateStore.clear(Common.REQUEST_ID)
    except Exception:
        logger.debug("Unable to clear request_id from StateStore", exc_info=True)
