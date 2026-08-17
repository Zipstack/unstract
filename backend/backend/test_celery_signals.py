"""Unit checks for the backend's Celery request_id signal handlers.

These are the producer half of the correlation chain: the HTTP request binds an
id (see ``middleware/test_request_id.py``), and these handlers carry it onto
every task the backend publishes and back off the message for tasks the
backend's *own* Celery workers run.

The handlers are written to fail open -- correlation plumbing must never break
task publishing -- which means a regression here is silent by construction: the
header simply stops being set and every worker log line reverts to
``request_id:-``. Nothing raises, so only assertions catch it.

Pure-logic: ``StateStore`` is a thread-local and the signals are called
directly, so no broker, worker or DB is involved.
"""

import pytest
from account_v2.constants import Common
from log_request_id import local as log_request_id_local
from utils.local_context import StateStore

from backend.celery_signals import (
    bind_request_id,
    clear_request_id,
    propagate_request_id,
)

REQUEST_ID = "6f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f"


class _Request:
    """Stands in for a Celery task ``Context``."""

    def __init__(self, request_id=None, headers=None):
        if request_id is not None:
            self.request_id = request_id
        self.headers = headers


class _Task:
    def __init__(self, request=None):
        self.request = request


@pytest.fixture(autouse=True)
def _clean_context():
    """Both stores are thread-local and shared across tests in a worker, so a
    leaked id would make a later test pass for the wrong reason.
    """
    yield
    for store_key in (Common.REQUEST_ID,):
        try:
            StateStore.clear(store_key)
        except AttributeError:
            pass
    if hasattr(log_request_id_local, "request_id"):
        del log_request_id_local.request_id


# Producer side: before_task_publish


def test_publish_injects_request_id_from_state_store():
    """The id bound by the HTTP middleware rides out on the task message."""
    StateStore.set(Common.REQUEST_ID, REQUEST_ID)
    headers = {}

    propagate_request_id(headers=headers)

    assert headers[Common.REQUEST_ID] == REQUEST_ID


def test_publish_is_a_noop_without_a_request_id():
    """Beat-scheduled publishes have no request in scope; the worker falls back
    to its own execution_id/task_id rather than receiving an empty header.
    """
    headers = {}

    propagate_request_id(headers=headers)

    assert headers == {}


def test_publish_does_not_clobber_an_explicit_header():
    """A caller that set the header deliberately outranks the ambient id."""
    StateStore.set(Common.REQUEST_ID, REQUEST_ID)
    headers = {Common.REQUEST_ID: "caller-supplied"}

    propagate_request_id(headers=headers)

    assert headers[Common.REQUEST_ID] == "caller-supplied"


def test_publish_tolerates_missing_headers():
    """``before_task_publish`` must never raise -- it would break the publish
    itself, taking the actual task down with the correlation plumbing.
    """
    propagate_request_id(headers=None)  # does not raise


# Consumer side: task_prerun / task_postrun on the backend's own workers


def test_prerun_binds_id_from_task_attribute():
    """Protocol v2 promotes custom headers to attributes on the Context."""
    bind_request_id(task=_Task(_Request(request_id=REQUEST_ID)))

    assert log_request_id_local.request_id == REQUEST_ID
    assert StateStore.get(Common.REQUEST_ID) == REQUEST_ID


def test_prerun_falls_back_to_raw_headers_mapping():
    """Version-safe path for when the header is not promoted to an attribute."""
    bind_request_id(task=_Task(_Request(headers={Common.REQUEST_ID: REQUEST_ID})))

    assert log_request_id_local.request_id == REQUEST_ID


def test_prerun_binding_makes_the_id_re_propagate():
    """Second-order effect that motivated the handler: a task the backend
    worker itself publishes must carry the inherited id onward, or the chain
    dies at the first backend-worker hop.
    """
    bind_request_id(task=_Task(_Request(request_id=REQUEST_ID)))
    headers = {}

    propagate_request_id(headers=headers)

    assert headers[Common.REQUEST_ID] == REQUEST_ID


def test_prerun_without_an_id_leaves_stores_untouched():
    """No header means no correlation to inherit -- and, importantly, no empty
    string bound over whatever the logger would otherwise show.
    """
    bind_request_id(task=_Task(_Request()))

    assert not hasattr(log_request_id_local, "request_id")
    assert StateStore.get(Common.REQUEST_ID) is None


def test_prerun_tolerates_a_task_without_a_request():
    bind_request_id(task=_Task(request=None))  # does not raise

    assert not hasattr(log_request_id_local, "request_id")


def test_postrun_clears_the_bound_id():
    """Celery reuses worker threads; a surviving id would mislabel the *next*
    task's logs with the previous task's correlation id.
    """
    bind_request_id(task=_Task(_Request(request_id=REQUEST_ID)))

    clear_request_id()

    assert not hasattr(log_request_id_local, "request_id")
    assert StateStore.get(Common.REQUEST_ID) is None


def test_postrun_is_safe_when_nothing_was_bound():
    clear_request_id()  # does not raise
