"""Worker half of the ``X-Request-ID`` correlation chain.

The backend's tests cover the producer side (injecting the id into a published
task's message headers). These cover what the worker does with it: preferring an
upstream header over a payload-derived id, refusing to fan out an id it derived
locally, clearing per-task state on a pooled thread, and re-emitting the id on
outbound internal-API calls.

Two of these pin regressions that were caught by review rather than by a test --
the propagatable gate, and the reset of that flag on task teardown.
"""

import pytest

from shared.clients.base_client import _current_request_id
from shared.infrastructure.logging.logger import (
    LogContext,
    WorkerLogger,
    _bind_task_context,
    _clear_task_context,
    _propagate_request_id_on_publish,
    _request_id_from_message,
)

HEADER_ID = "11111111-2222-4333-8444-555555555555"
PAYLOAD_ID = "99999999-8888-4777-8666-555555555555"
TASK_ID = "celery-task-id-0001"


class _Request:
    """Stands in for ``celery.app.task.Context``.

    Celery may expose a custom message header as an attribute or leave it only
    in the raw ``headers`` mapping, so both shapes are constructible here.
    """

    def __init__(self, request_id=None, headers=None, **payload):
        if request_id is not None:
            self.request_id = request_id
        self.headers = headers
        self.__dict__.update(payload)


class _Task:
    def __init__(self, request):
        self.request = request
        self.name = "workers.test.task"


@pytest.fixture(autouse=True)
def _isolate_context():
    """Each test starts and ends on a clean thread-local context."""
    WorkerLogger.clear_context()
    yield
    WorkerLogger.clear_context()


# ---------------------------------------------------------------------------
# Reading the id off the message
# ---------------------------------------------------------------------------


def test_header_attribute_is_read():
    assert _request_id_from_message(_Task(_Request(request_id=HEADER_ID))) == HEADER_ID


def test_raw_headers_mapping_is_the_fallback():
    task = _Task(_Request(headers={"request_id": HEADER_ID}))

    assert _request_id_from_message(task) == HEADER_ID


def test_absent_header_reads_as_none():
    assert _request_id_from_message(_Task(_Request())) is None


def test_missing_request_object_does_not_raise():
    class _Bare:
        request = None

    assert _request_id_from_message(_Bare()) is None


# ---------------------------------------------------------------------------
# Binding: precedence and the propagatable gate
# ---------------------------------------------------------------------------


def test_header_id_wins_over_payload_and_is_propagatable():
    """An upstream id is the authoritative correlation key, so it takes
    precedence over anything derivable from the payload.
    """
    task = _Task(_Request(request_id=HEADER_ID))

    _bind_task_context(TASK_ID, task, (), {"file_execution_id": PAYLOAD_ID})

    ctx = WorkerLogger.get_context()
    assert ctx.request_id == HEADER_ID
    assert ctx.request_id_propagatable is True


def test_payload_id_is_used_but_is_not_propagatable():
    """A payload-derived id correlates this task only. Marking it propagatable
    would stamp it onto child tasks and override *their* own file_execution_id.
    """
    task = _Task(_Request())

    _bind_task_context(TASK_ID, task, (), {"file_execution_id": PAYLOAD_ID})

    ctx = WorkerLogger.get_context()
    assert ctx.request_id == PAYLOAD_ID
    assert ctx.request_id_propagatable is False


def test_task_id_is_the_last_resort_and_is_not_propagatable():
    _bind_task_context(TASK_ID, _Task(_Request()), (), {})

    ctx = WorkerLogger.get_context()
    assert ctx.request_id == TASK_ID
    assert ctx.request_id_propagatable is False


def test_a_raising_request_object_still_binds_the_task_id():
    """The whole resolution sits inside a try precisely so a malformed message
    cannot leave the *previous* task's id bound on a reused thread.
    """

    class _Exploding:
        @property
        def request(self):
            raise RuntimeError("malformed message")

    WorkerLogger.set_context(LogContext(request_id="stale-previous-task"))

    _bind_task_context(TASK_ID, _Exploding(), (), {})

    ctx = WorkerLogger.get_context()
    assert ctx.request_id == TASK_ID
    assert ctx.request_id_propagatable is False


# ---------------------------------------------------------------------------
# Re-publishing to child tasks
# ---------------------------------------------------------------------------


def test_propagatable_id_is_stamped_onto_a_child_task():
    WorkerLogger.set_context(
        LogContext(request_id=HEADER_ID, request_id_propagatable=True)
    )
    headers = {}

    _propagate_request_id_on_publish(headers=headers)

    assert headers["request_id"] == HEADER_ID


def test_locally_derived_id_is_not_stamped_onto_a_child_task():
    """The regression the gate exists for: without it a scheduler-originated
    task fans its own task_id out over every child's own correlation id.
    """
    WorkerLogger.set_context(
        LogContext(request_id=TASK_ID, request_id_propagatable=False)
    )
    headers = {}

    _propagate_request_id_on_publish(headers=headers)

    assert headers == {}


def test_an_id_the_caller_already_set_is_left_alone():
    WorkerLogger.set_context(
        LogContext(request_id=HEADER_ID, request_id_propagatable=True)
    )
    headers = {"request_id": "explicitly-set-by-caller"}

    _propagate_request_id_on_publish(headers=headers)

    assert headers["request_id"] == "explicitly-set-by-caller"


def test_no_headers_mapping_is_a_no_op():
    WorkerLogger.set_context(
        LogContext(request_id=HEADER_ID, request_id_propagatable=True)
    )

    _propagate_request_id_on_publish(headers=None)  # does not raise


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


def test_teardown_resets_the_propagatable_flag():
    """Prefork/thread workers reuse the thread. A flag left True would let the
    next task's locally-derived id fan out as though it came from upstream.
    """
    _bind_task_context(TASK_ID, _Task(_Request(request_id=HEADER_ID)), (), {})

    _clear_task_context()

    ctx = WorkerLogger.get_context()
    assert ctx.request_id is None
    assert ctx.request_id_propagatable is False


def test_a_child_published_after_teardown_inherits_nothing():
    _bind_task_context(TASK_ID, _Task(_Request(request_id=HEADER_ID)), (), {})
    _clear_task_context()
    headers = {}

    _propagate_request_id_on_publish(headers=headers)

    assert headers == {}


# ---------------------------------------------------------------------------
# Outbound internal-API calls
# ---------------------------------------------------------------------------


def test_bound_id_is_offered_to_outbound_calls():
    _bind_task_context(TASK_ID, _Task(_Request(request_id=HEADER_ID)), (), {})

    assert _current_request_id() == HEADER_ID


def test_placeholder_id_sends_no_header():
    """``"-"`` is the formatter's empty rendering, not an id -- sending it would
    put a meaningless X-Request-ID on the wire.
    """
    WorkerLogger.set_context(LogContext(request_id="-"))

    assert _current_request_id() is None


def test_no_context_sends_no_header():
    assert _current_request_id() is None
