"""Tests for the backend executor-RPC adapter (UN-3607).

The dispatch contract (never-raises / result interpretation), the routing, and the
Flipt gate matrix live ONCE in the shared module and are covered in
``workers/tests/test_executor_rpc.py`` against a fake transport. This suite pins the
**backend half**: the :class:`DjangoQueueTransport` (enqueue via the ORM, poll
``PgTaskResult`` → ``ExecResultRow``), the per-side gate (master switch =
``settings.PG_QUEUE_TRANSPORT_ENABLED``), and the factory wiring.
"""

from unittest.mock import MagicMock, patch

from unstract.workflow_execution.executor_rpc import ExecResultRow

from pg_queue.executor_rpc import (
    DjangoQueueTransport,
    RoutingExecutionDispatcher,
    get_executor_dispatcher,
    resolve_executor_transport,
)

_MOD = "pg_queue.executor_rpc"


def _ctx() -> MagicMock:
    c = MagicMock()
    c.executor_name = "legacy"
    c.run_id = "r"
    c.to_dict.return_value = {"run_id": "r"}
    return c


class TestDjangoQueueTransportEnqueue:
    def test_enqueue_calls_enqueue_task_with_request_reply_fields(self):
        with patch(f"{_MOD}.enqueue_task") as enq:
            DjangoQueueTransport().enqueue(
                queue="celery_executor_legacy", context=_ctx(), org_id="org9",
                reply_key="rk1",
            )
        kw = enq.call_args.kwargs
        assert kw["task_name"] == "execute_extraction"
        assert kw["queue"] == "celery_executor_legacy"
        assert kw["args"] == [{"run_id": "r"}]
        assert kw["org_id"] == "org9"
        assert kw["reply_key"] == "rk1"
        assert kw["task_id"] is None and kw["on_success"] is None

    def test_enqueue_carries_continuations(self):
        spec = {"task_name": "ide_prompt_complete", "kwargs": {}, "queue": "ide_callback"}
        with patch(f"{_MOD}.enqueue_task") as enq:
            DjangoQueueTransport().enqueue(
                queue="celery_executor_legacy", context=_ctx(), org_id="o",
                on_success=spec, task_id="tid-7",
            )
        kw = enq.call_args.kwargs
        assert kw["on_success"] == spec and kw["task_id"] == "tid-7"
        assert kw["reply_key"] is None  # callback dispatch, not request-reply


class TestDjangoQueueTransportWait:
    def test_present_row_folds_to_exec_result_row(self):
        row = MagicMock(status="completed", result={"a": 1}, error="")
        qs = MagicMock()
        qs.filter.return_value.first.return_value = row
        with patch(f"{_MOD}.PgTaskResult", MagicMock(objects=qs)):
            out = DjangoQueueTransport().wait_for_result("rk", timeout=5)
        assert isinstance(out, ExecResultRow)
        assert out.status == "completed" and out.result == {"a": 1}

    def test_timeout_returns_none(self):
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None  # never appears
        with (
            patch(f"{_MOD}.PgTaskResult", MagicMock(objects=qs)),
            patch(f"{_MOD}.close_old_connections"),
        ):
            # timeout=0 → first poll misses, remaining <= 0 → None (no sleep).
            assert DjangoQueueTransport().wait_for_result("rk", timeout=0) is None

    def test_multi_iteration_poll_misses_then_hits(self):
        # The load-bearing backoff path: a miss, then a hit on the next poll — the
        # connection is released (close_old_connections) and it sleeps once between.
        row = MagicMock(status="completed", result={"a": 1}, error="")
        qs = MagicMock()
        qs.filter.return_value.first.side_effect = [None, row]
        with (
            patch(f"{_MOD}.PgTaskResult", MagicMock(objects=qs)),
            patch(f"{_MOD}.close_old_connections") as cl,
            patch("unstract.workflow_execution.executor_rpc.time.sleep") as slp,
        ):
            out = DjangoQueueTransport().wait_for_result("rk", timeout=5)
        assert isinstance(out, ExecResultRow) and out.result == {"a": 1}
        cl.assert_called_once()  # between_polls released the conn on the miss
        slp.assert_called_once()  # slept once between the two polls


class TestResolveExecutorTransport:
    @staticmethod
    def _gate(on: bool):
        s = MagicMock()
        s.PG_QUEUE_TRANSPORT_ENABLED = on
        return patch(f"{_MOD}.settings", s)

    def test_reads_settings_master_gate_on(self):
        with self._gate(True), patch(
            f"{_MOD}.resolve_pg_transport", return_value=True
        ) as r:
            assert resolve_executor_transport(_ctx()) is True
        assert r.call_args.kwargs["master_gate_enabled"] is True

    def test_reads_settings_master_gate_off(self):
        with self._gate(False), patch(
            f"{_MOD}.resolve_pg_transport", return_value=False
        ) as r:
            resolve_executor_transport(_ctx())
        assert r.call_args.kwargs["master_gate_enabled"] is False


class TestFactoryWiring:
    def test_factory_wires_routing_with_django_transport(self):
        d = get_executor_dispatcher(celery_app="app")
        assert isinstance(d, RoutingExecutionDispatcher)
        # PG dispatcher uses the backend ORM transport; gate = the settings resolver.
        assert isinstance(d._pg._transport, DjangoQueueTransport)
        assert d._resolve is resolve_executor_transport
