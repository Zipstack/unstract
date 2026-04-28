"""Tests for request_id binding in the workers shared logger.

Covers UN-3435 fixes:
  * RequestIDFilter fallback chain (record extra > LogContext > "-").
  * _extract_request_id key-priority scan across positional args, kwargs,
    nested dicts, dataclasses, and signature-bound positional names.
  * _clear_task_context resets only the task-scoped fields (request_id,
    task_id) and preserves baseline LogContext fields.
  * Signal install is idempotent under concurrent calls.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from unittest.mock import MagicMock

import pytest

from shared.infrastructure.logging.logger import (
    LogContext,
    RequestIDFilter,
    WorkerLogger,
    _bind_task_context,
    _clear_task_context,
    _coerce_id,
    _extract_request_id,
    _install_celery_request_id_signals,
)


@pytest.fixture(autouse=True)
def _clean_context():
    """Reset thread-local context between tests."""
    WorkerLogger.clear_context()
    yield
    WorkerLogger.clear_context()


def _record() -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, "p", 1, "m", None, None)


# --- RequestIDFilter fallback chain ----------------------------------------


def test_filter_uses_record_extra_when_present():
    WorkerLogger.update_context(request_id="from-context")
    rec = _record()
    rec.request_id = "from-extra"
    RequestIDFilter().filter(rec)
    assert rec.request_id == "from-extra"


def test_filter_falls_back_to_log_context():
    WorkerLogger.update_context(request_id="from-context")
    rec = _record()
    RequestIDFilter().filter(rec)
    assert rec.request_id == "from-context"


def test_filter_returns_dash_when_unset():
    rec = _record()
    RequestIDFilter().filter(rec)
    assert rec.request_id == "-"


# --- _coerce_id -------------------------------------------------------------


def test_coerce_id_accepts_str_int_uuid():
    from uuid import UUID

    assert _coerce_id("abc") == "abc"
    assert _coerce_id(42) == "42"
    u = UUID("12345678-1234-5678-1234-567812345678")
    assert _coerce_id(u) == str(u)


def test_coerce_id_rejects_unsupported_types():
    assert _coerce_id(None) is None
    assert _coerce_id("") is None
    assert _coerce_id(["x"]) is None
    assert _coerce_id({"x": 1}) is None
    assert _coerce_id(object()) is None


# --- _extract_request_id key-priority scans ---------------------------------


def test_extract_picks_request_id_first():
    assert (
        _extract_request_id(
            (), {"request_id": "r", "file_execution_id": "f", "execution_id": "e"}
        )
        == "r"
    )


def test_extract_falls_back_to_file_execution_id():
    assert _extract_request_id((), {"file_execution_id": "f"}) == "f"


def test_extract_returns_none_when_no_keys_match():
    assert _extract_request_id((), {"unrelated": "x"}) is None


def test_extract_searches_dict_args():
    assert _extract_request_id(({"request_id": "from-arg"},), {}) == "from-arg"


def test_extract_searches_nested_dict_in_kwargs():
    assert (
        _extract_request_id((), {"context": {"execution_id": "nested"}}) == "nested"
    )


def test_extract_top_level_kwargs_beats_nested_dict_when_same_key():
    # Same key in two containers: container order doesn't matter since
    # priority is by key.  This case both have execution_id, top-level wins
    # via container order tiebreak.
    assert (
        _extract_request_id(
            (), {"execution_id": "top", "context": {"execution_id": "nested"}}
        )
        == "top"
    )


def test_extract_priority_is_by_key_not_container_order():
    # Higher-priority key in nested dict beats lower-priority key in
    # top-level kwargs.  Original implementation walked containers first,
    # which would incorrectly return "B" here.
    result = _extract_request_id(
        (),
        {
            "context": {"file_execution_id": "FE"},
            "meta": {"execution_id": "EX"},
        },
    )
    assert result == "FE"


def test_extract_via_signature_bound_positional_args():
    """P0 regression: send_task('async_execute_bin', args=[schema, wf, exec, files])
    must surface execution_id even though args are all positional strings.
    """

    def execute_bin(
        schema_name: str,
        workflow_id: str,
        execution_id: str,
        file_hash_in_str: dict,
        scheduled: bool = False,
    ):
        pass

    fake_task = MagicMock()
    fake_task.run = execute_bin

    args = ("org-schema", "wf-id", "exec-id-123", {})
    kwargs = {"scheduled": False}

    assert _extract_request_id(args, kwargs, task=fake_task) == "exec-id-123"


def test_extract_signature_bind_failure_falls_back_to_shape_scan():
    """If task.run uses *args/**kwargs only, signature.bind_partial succeeds
    but populates 'args'/'kwargs' as keys -- we still find ids via the dict-
    args / nested-dict scans.
    """

    def variadic(*args, **kwargs):
        pass

    fake_task = MagicMock()
    fake_task.run = variadic

    # Even though signature can't name positional ids, dict args still scan.
    args = ({"execution_id": "from-dict-arg"},)
    assert _extract_request_id(args, {}, task=fake_task) == "from-dict-arg"


def test_extract_supports_dataclass_arg():
    @dataclasses.dataclass
    class Ctx:
        execution_id: str
        unrelated: int = 0

    arg = Ctx(execution_id="from-dataclass")
    assert _extract_request_id((arg,), {}) == "from-dataclass"


def test_extract_rejects_object_value():
    """Non-id-typed values (objects, lists) at id keys must be ignored,
    not stringified as '<object at 0x...>' into the log line.
    """

    class Weird:
        pass

    assert _extract_request_id((), {"request_id": Weird()}) is None
    assert _extract_request_id((), {"execution_id": ["x"]}) is None


# --- task_prerun / task_postrun semantics -----------------------------------


def test_bind_uses_extracted_value():
    _bind_task_context(
        task_id="celery-tid",
        task=None,
        args=({"request_id": "wf-rid"},),
        kwargs={},
    )
    rec = _record()
    RequestIDFilter().filter(rec)
    assert rec.request_id == "wf-rid"


def test_bind_falls_back_to_task_id_when_payload_has_no_id():
    _bind_task_context(task_id="celery-tid", task=None, args=(), kwargs={})
    rec = _record()
    RequestIDFilter().filter(rec)
    assert rec.request_id == "celery-tid"


def test_bind_swallows_extraction_errors():
    """A misbehaving payload must not break task execution -- _bind must
    fall back to task_id rather than propagate the exception.
    """

    class BadDict(dict):
        def get(self, *_a, **_kw):
            raise RuntimeError("intentional")

    bad = BadDict()
    bad["request_id"] = "x"  # populated but get() raises
    _bind_task_context(
        task_id="fallback-tid", task=None, args=(bad,), kwargs={}
    )
    rec = _record()
    RequestIDFilter().filter(rec)
    assert rec.request_id == "fallback-tid"


def test_clear_preserves_baseline_worker_name():
    WorkerLogger.set_context(LogContext(worker_name="executor-worker-v2"))
    _bind_task_context(
        task_id="tid",
        task=None,
        args=({"request_id": "rid"},),
        kwargs={},
    )
    ctx = WorkerLogger.get_context()
    assert ctx.worker_name == "executor-worker-v2"
    assert ctx.request_id == "rid"

    _clear_task_context()
    ctx = WorkerLogger.get_context()
    assert ctx is not None
    assert ctx.worker_name == "executor-worker-v2", "baseline lost on clear"
    assert ctx.request_id is None
    assert ctx.task_id is None


def test_clear_then_filter_returns_dash():
    _bind_task_context(
        task_id="tid",
        task=None,
        args=({"request_id": "rid"},),
        kwargs={},
    )
    _clear_task_context()
    rec = _record()
    RequestIDFilter().filter(rec)
    assert rec.request_id == "-"


# --- Signal install thread safety ------------------------------------------


def test_install_is_idempotent_under_concurrency():
    # lru_cache makes _install... callable many times safely; just verify
    # no errors and a consistent post-state.
    _install_celery_request_id_signals.cache_clear()

    errors: list[Exception] = []

    def install():
        try:
            _install_celery_request_id_signals()
        except Exception as exc:  # pragma: no cover - guard
            errors.append(exc)

    threads = [threading.Thread(target=install) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    info = _install_celery_request_id_signals.cache_info()
    # 20 calls, 1 miss, 19 hits regardless of thread interleaving.
    assert info.misses == 1
    assert info.hits == 19
