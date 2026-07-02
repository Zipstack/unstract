"""Tests for the executor-RPC dispatch (UN-3607 shared module + the workers adapter).

The gate + reply_key/timeout orchestration + routing now live ONCE in
``unstract.workflow_execution.executor_rpc`` (shared by backend + workers). This
suite is the home for the **shared contract** (tested against a fake transport, so
the dispatch never-raises / result-interpretation / routing logic is verified a
single time, not per-mirror) PLUS the **workers adapter** (``PgClientQueueTransport``
+ the env-master-gate ``resolve_executor_transport`` + the ``get_executor_dispatcher``
wiring). The backend adapter is tested in ``backend/pg_queue/tests/test_executor_rpc.py``.
"""

from unittest.mock import MagicMock, patch

import pytest
from queue_backend.pg_queue.executor_rpc import (
    PgClientQueueTransport,
    RoutingExecutionDispatcher,
    get_executor_dispatcher,
    resolve_executor_transport,
)
from unstract.core.execution_dispatch import DispatchHandle, signature_to_continuation
from unstract.workflow_execution.executor_rpc import (
    ExecResultRow,
    PgExecutionDispatcher,
    resolve_pg_transport,
)

_WMOD = "queue_backend.pg_queue.executor_rpc"
_SMOD = "unstract.workflow_execution.executor_rpc"


def _ctx(org: str | None = "org1") -> MagicMock:
    c = MagicMock()
    c.executor_name = "legacy"
    c.run_id = "run-1"
    c.organization_id = org
    c.to_dict.return_value = {"run_id": "run-1"}
    return c


def _ok_result() -> dict:
    return {"success": True, "data": {"x": 1}, "metadata": {}, "error": None}


def _completed(result: dict) -> ExecResultRow:
    return ExecResultRow(status="completed", result=result, error="")


class _FakeTransport:
    """Records ``enqueue`` calls and returns a configured result for the poll.

    Lets the shared dispatcher's logic be exercised without any DB.
    """

    def __init__(self, *, wait_return=None, wait_raises=None, enqueue_raises=None):
        self.enqueue_calls: list[dict] = []
        self.wait_timeouts: list[float] = []
        self._wait_return = wait_return
        self._wait_raises = wait_raises
        self._enqueue_raises = enqueue_raises

    def enqueue(self, **kwargs) -> None:
        self.enqueue_calls.append(kwargs)
        if self._enqueue_raises is not None:
            raise self._enqueue_raises

    def wait_for_result(self, reply_key, timeout):
        self.wait_timeouts.append(timeout)
        if self._wait_raises is not None:
            raise self._wait_raises
        return self._wait_return


# --- Shared contract: PgExecutionDispatcher never-raises + result interpretation ---


class TestSharedDispatchContract:
    def test_enqueue_failure_returns_failure_not_raise(self):
        d = PgExecutionDispatcher(_FakeTransport(enqueue_raises=RuntimeError("db down")))
        res = d.dispatch(_ctx(), timeout=5)
        assert res.success is False and "RuntimeError" in res.error

    def test_wait_failure_returns_failure_not_raise(self):
        d = PgExecutionDispatcher(_FakeTransport(wait_raises=RuntimeError("conn died")))
        res = d.dispatch(_ctx(), timeout=5)
        assert res.success is False and "RuntimeError" in res.error

    def test_timeout_returns_failure(self):
        d = PgExecutionDispatcher(_FakeTransport(wait_return=None))
        res = d.dispatch(_ctx(), timeout=3)
        assert res.success is False and "within 3s" in res.error

    def test_completed_row_returns_result(self):
        d = PgExecutionDispatcher(_FakeTransport(wait_return=_completed(_ok_result())))
        assert d.dispatch(_ctx(), timeout=5).success is True

    def test_failed_row_returns_error(self):
        row = ExecResultRow(status="failed", result=None, error="boom")
        res = PgExecutionDispatcher(_FakeTransport(wait_return=row)).dispatch(_ctx(), timeout=5)
        assert res.success is False and res.error == "boom"

    def test_failed_row_empty_error_falls_back(self):
        row = ExecResultRow(status="failed", result=None, error="")
        res = PgExecutionDispatcher(_FakeTransport(wait_return=row)).dispatch(_ctx(), timeout=5)
        assert res.success is False and "executor task failed" in res.error

    def test_completed_but_result_none_is_failure(self):
        row = ExecResultRow(status="completed", result=None, error="")
        assert PgExecutionDispatcher(_FakeTransport(wait_return=row)).dispatch(_ctx(), timeout=5).success is False

    def test_malformed_completed_row_is_failure_not_raise(self):
        d = PgExecutionDispatcher(_FakeTransport(wait_return=_completed({"bad": "shape"})))
        res = d.dispatch(_ctx(), timeout=5)
        assert res.success is False and "Malformed" in res.error

    def test_timeout_none_reads_env_then_default(self, monkeypatch):
        monkeypatch.setenv("EXECUTOR_RESULT_TIMEOUT", "42")
        t = _FakeTransport(wait_return=None)
        PgExecutionDispatcher(t).dispatch(_ctx())  # no explicit timeout
        assert t.wait_timeouts == [42]

    def test_timeout_none_bad_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("EXECUTOR_RESULT_TIMEOUT", "not-an-int")
        t = _FakeTransport(wait_return=None)
        PgExecutionDispatcher(t).dispatch(_ctx())  # must not raise
        assert t.wait_timeouts == [3600]

    def test_dispatch_request_reply_enqueues_reply_key_only(self):
        t = _FakeTransport(wait_return=_completed(_ok_result()))
        PgExecutionDispatcher(t).dispatch(_ctx(), timeout=5)
        (kw,) = t.enqueue_calls
        assert kw["queue"] == "celery_executor_legacy" and kw["org_id"] == "org1"
        assert kw["reply_key"]  # request-reply marker
        assert kw.get("task_id") is None and kw.get("on_success") is None

    def test_dispatch_async_is_fire_and_forget(self):
        t = _FakeTransport()
        task_id = PgExecutionDispatcher(t).dispatch_async(_ctx())
        (kw,) = t.enqueue_calls
        assert kw["task_id"] == task_id and kw.get("reply_key") is None
        assert kw.get("on_success") is None and kw.get("on_error") is None

    def test_dispatch_async_propagates_enqueue_failure(self):
        # Documented asymmetry vs the never-raises dispatch: a fire-and-forget enqueue
        # error propagates (the caller has no result object to fail into).
        t = _FakeTransport(enqueue_raises=RuntimeError("db down"))
        with pytest.raises(RuntimeError, match="db down"):
            PgExecutionDispatcher(t).dispatch_async(_ctx())

    @staticmethod
    def _sig(task: str):
        return MagicMock(
            task=task, args=(), kwargs={"callback_kwargs": {"room": "r1"}},
            options={"queue": "ide_callback"},
        )

    def test_dispatch_with_callback_translates_both_signatures(self):
        t = _FakeTransport()
        handle = PgExecutionDispatcher(t).dispatch_with_callback(
            _ctx(), on_success=self._sig("ide_prompt_complete"),
            on_error=self._sig("ide_prompt_error"), task_id="tid-7",
        )
        assert handle.id == "tid-7"
        (kw,) = t.enqueue_calls
        assert kw["on_success"] == {
            "task_name": "ide_prompt_complete",
            "kwargs": {"callback_kwargs": {"room": "r1"}},
            "queue": "ide_callback",
        }
        assert kw["on_error"]["task_name"] == "ide_prompt_error"  # on_error translated
        assert kw["task_id"] == "tid-7" and kw.get("reply_key") is None

    def test_dispatch_with_callback_defaults_task_id(self):
        t = _FakeTransport()
        handle = PgExecutionDispatcher(t).dispatch_with_callback(
            _ctx(), on_success=self._sig("ide_prompt_complete")
        )
        # No task_id passed → a uuid is generated, echoed on the handle AND the payload.
        assert handle.id
        assert t.enqueue_calls[0]["task_id"] == handle.id


# --- Shared gate: resolve_pg_transport (single Flipt flag, fail-closed) ---


class TestResolvePgTransport:
    def test_flipt_unavailable_is_celery(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "false")
        with patch(f"{_SMOD}.check_feature_flag_status") as flag:
            assert resolve_pg_transport(_ctx()) is False
            flag.assert_not_called()

    def test_flag_true_is_pg_keyed_on_org(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(f"{_SMOD}.check_feature_flag_status", return_value=True) as flag:
            assert resolve_pg_transport(_ctx("orgX")) is True
            assert flag.call_args.kwargs["entity_id"] == "orgX"
            assert flag.call_args.kwargs["flag_key"] == "pg_queue_enabled"

    def test_flag_false_is_celery(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(f"{_SMOD}.check_feature_flag_status", return_value=False):
            assert resolve_pg_transport(_ctx()) is False

    def test_flipt_error_fails_closed(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(f"{_SMOD}.check_feature_flag_status", side_effect=RuntimeError("x")):
            assert resolve_pg_transport(_ctx()) is False

    def test_org_less_context_buckets_on_run_id(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(f"{_SMOD}.check_feature_flag_status", return_value=True) as flag:
            assert resolve_pg_transport(_ctx(org=None)) is True
        assert flag.call_args.kwargs["entity_id"] == "run-1"
        assert "organization_id" not in flag.call_args.kwargs["context"]


# --- Shared routing: RoutingExecutionDispatcher (zero-regression) ---


class TestRoutingDispatch:
    @staticmethod
    def _build(route_to_pg: bool):
        celery, pg = MagicMock(), MagicMock()
        d = RoutingExecutionDispatcher(
            celery=celery, pg=pg, resolve=lambda _ctx: route_to_pg
        )
        return d, celery, pg

    def test_gate_off_forwards_timeout_and_headers_to_celery(self):
        d, celery, pg = self._build(route_to_pg=False)
        ctx = _ctx()
        hdrs = {"x-fairness-key": {"org_id": "o"}}
        d.dispatch(ctx, timeout=9, headers=hdrs)
        celery.dispatch.assert_called_once_with(ctx, timeout=9, headers=hdrs)
        pg.dispatch.assert_not_called()

    def test_gate_on_passes_timeout_to_pg_and_drops_headers(self):
        d, celery, pg = self._build(route_to_pg=True)
        ctx = _ctx()
        d.dispatch(ctx, timeout=7, headers={"x-fairness-key": {"o": 1}})
        pg.dispatch.assert_called_once_with(ctx, timeout=7)  # headers dropped
        celery.dispatch.assert_not_called()

    def test_async_and_callback_stay_celery_when_gate_off(self):
        d, celery, pg = self._build(route_to_pg=False)
        d.dispatch_async(_ctx(), headers={"h": 1})
        d.dispatch_with_callback(_ctx(), on_success="s", on_error="e")
        celery.dispatch_async.assert_called_once()
        celery.dispatch_with_callback.assert_called_once()
        pg.dispatch_async.assert_not_called()
        pg.dispatch_with_callback.assert_not_called()

    def test_async_and_callback_route_to_pg_when_gated(self):
        d, celery, pg = self._build(route_to_pg=True)
        d.dispatch_async(_ctx())
        d.dispatch_with_callback(_ctx(), on_success="s", on_error="e", task_id="t")
        pg.dispatch_async.assert_called_once()
        pg.dispatch_with_callback.assert_called_once()
        assert "headers" not in pg.dispatch_with_callback.call_args.kwargs
        celery.dispatch_async.assert_not_called()
        celery.dispatch_with_callback.assert_not_called()


# --- Workers adapter: PgClientQueueTransport + env gate + factory wiring ---


class TestWorkersAdapter:
    @staticmethod
    def _ctx():
        c = MagicMock()
        c.executor_name = "legacy"
        c.run_id = "r"
        c.to_dict.return_value = {"run_id": "r"}
        return c

    @staticmethod
    def _client():
        client = MagicMock()
        client.__enter__.return_value = client  # `with PgQueueClient() as c`
        return client

    def test_enqueue_sends_queue_payload_and_org(self):
        client = self._client()
        with patch(f"{_WMOD}.PgQueueClient", return_value=client):
            PgClientQueueTransport().enqueue(
                queue="celery_executor_legacy", context=self._ctx(),
                org_id="org9", reply_key="rk1",
            )
        client.send.assert_called_once()
        queue_arg, payload_arg = client.send.call_args.args[:2]
        assert queue_arg == "celery_executor_legacy"
        assert client.send.call_args.kwargs["org_id"] == "org9"
        assert payload_arg["task_name"] == "execute_extraction"
        assert payload_arg["args"] == [{"run_id": "r"}]
        assert payload_arg["reply_key"] == "rk1"

    def test_enqueue_carries_continuations(self):
        client = self._client()
        spec = {"task_name": "ide_prompt_complete", "kwargs": {}, "queue": "ide_callback"}
        with patch(f"{_WMOD}.PgQueueClient", return_value=client):
            PgClientQueueTransport().enqueue(
                queue="celery_executor_legacy", context=self._ctx(), org_id="o",
                on_success=spec, task_id="tid-7",
            )
        payload = client.send.call_args.args[1]
        assert payload["on_success"] == spec and payload["task_id"] == "tid-7"
        assert "reply_key" not in payload  # callback dispatch, not request-reply

    def test_wait_for_result_folds_dict_to_row(self):
        rb = MagicMock()
        rb.__enter__.return_value = rb
        rb.wait_for_result.return_value = {"status": "completed", "result": {"a": 1}, "error": ""}
        with patch(f"{_WMOD}.PgResultBackend", return_value=rb):
            row = PgClientQueueTransport().wait_for_result("rk", 5)
        assert isinstance(row, ExecResultRow)
        assert row.status == "completed" and row.result == {"a": 1}

    def test_wait_for_result_none_passes_through(self):
        rb = MagicMock()
        rb.__enter__.return_value = rb
        rb.wait_for_result.return_value = None
        with patch(f"{_WMOD}.PgResultBackend", return_value=rb):
            assert PgClientQueueTransport().wait_for_result("rk", 5) is None

    def test_resolve_delegates_to_shared_flipt_resolver_true(self):
        with patch(f"{_WMOD}.resolve_pg_transport", return_value=True) as r:
            assert resolve_executor_transport(self._ctx()) is True
        r.assert_called_once()
        # No env master-gate is threaded any more — Flipt is the sole gate.
        assert "master_gate_enabled" not in r.call_args.kwargs

    def test_resolve_delegates_to_shared_flipt_resolver_false(self):
        with patch(f"{_WMOD}.resolve_pg_transport", return_value=False):
            assert resolve_executor_transport(self._ctx()) is False

    def test_factory_wires_routing_with_workers_transport(self):
        d = get_executor_dispatcher(celery_app="app")
        assert isinstance(d, RoutingExecutionDispatcher)
        # The PG dispatcher is wired with the workers psycopg2 transport, and the gate
        # is the workers' Flipt resolver.
        assert isinstance(d._pg._transport, PgClientQueueTransport)
        assert d._resolve is resolve_executor_transport


# --- Core helpers (unchanged; the shared signature/handle primitives) ---


class TestSharedDispatchHelpers:
    def test_signature_none_passes_through(self):
        assert signature_to_continuation(None) is None

    def test_signature_translates_task_kwargs_and_queue(self):
        sig = MagicMock(task="ide_prompt_complete", args=(),
                        kwargs={"callback_kwargs": {"room": "r1"}},
                        options={"queue": "ide_callback"})
        assert signature_to_continuation(sig) == {
            "task_name": "ide_prompt_complete",
            "kwargs": {"callback_kwargs": {"room": "r1"}},
            "queue": "ide_callback",
        }

    def test_signature_missing_queue_fails_fast(self):
        sig = MagicMock(task="ide_prompt_complete", kwargs={}, options={"queue": ""})
        with pytest.raises(ValueError, match="no queue"):
            signature_to_continuation(sig)

    def test_signature_missing_task_fails_fast(self):
        sig = MagicMock(task=None, kwargs={}, options={"queue": "ide_callback"})
        with pytest.raises(ValueError, match="no task name"):
            signature_to_continuation(sig)

    def test_signature_with_positional_args_fails_fast(self):
        sig = MagicMock(task="ide_prompt_complete", args=("pos",), kwargs={},
                        options={"queue": "ide_callback"})
        with pytest.raises(ValueError, match="positional args"):
            signature_to_continuation(sig)

    def test_dispatch_handle_exposes_only_id(self):
        handle = DispatchHandle("tid-1")
        assert handle.id == "tid-1"
        with pytest.raises(AttributeError):
            handle.result = 1  # type: ignore[attr-defined]
