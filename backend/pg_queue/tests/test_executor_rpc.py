"""Tests for the executor-RPC transport routing (Phase 9).

DB-free: settings / Flipt / the sub-dispatchers are mocked. Pins the gate's
fail-closed matrix and — the load-bearing zero-regression property — that with
the gate off ``RoutingExecutionDispatcher`` delegates EVERY mode to the unchanged
Celery ``ExecutionDispatcher`` and never touches the PG path.
"""

from unittest.mock import MagicMock, patch

from pg_queue.executor_rpc import (
    PgExecutionDispatcher,
    RoutingExecutionDispatcher,
    resolve_executor_transport,
)

_MOD = "pg_queue.executor_rpc"


def _completed(result: dict) -> MagicMock:
    return MagicMock(status="completed", result=result, error="")


def _ok_result() -> dict:
    return {"success": True, "data": {"x": 1}, "metadata": {}, "error": None}


class TestPgExecutionDispatcherDispatch:
    """The load-bearing contract: never raises; timeout/failure → failure result.

    DB-free — ``enqueue_task`` and ``_wait_for_result`` are mocked.
    """

    @staticmethod
    def _ctx() -> MagicMock:
        c = MagicMock()
        c.executor_name = "legacy"
        c.run_id = "r"
        c.organization_id = "o"
        c.to_dict.return_value = {"run_id": "r"}
        return c

    def test_enqueue_failure_returns_failure_not_raise(self):
        with patch(f"{_MOD}.enqueue_task", side_effect=RuntimeError("db down")):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert "RuntimeError" in res.error

    def test_timeout_returns_failure(self):
        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=None),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=3)
        assert res.success is False
        assert "within 3s" in res.error

    def test_completed_row_returns_result(self):
        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(
                PgExecutionDispatcher, "_wait_for_result",
                return_value=_completed(_ok_result()),
            ),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is True

    def test_failed_row_returns_error(self):
        row = MagicMock(status="failed", result=None, error="boom")
        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=row),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert res.error == "boom"

    def test_failed_row_empty_error_falls_back(self):
        row = MagicMock(status="failed", result=None, error="")
        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=row),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert "executor task failed" in res.error

    def test_completed_but_result_none_is_failure(self):
        row = MagicMock(status="completed", result=None, error="")
        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=row),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False

    def test_malformed_completed_row_is_failure_not_raise(self):
        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(
                PgExecutionDispatcher, "_wait_for_result",
                return_value=_completed({"bad": "shape"}),
            ),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert "Malformed" in res.error

    def test_timeout_none_reads_env_then_default(self, monkeypatch):
        monkeypatch.setenv("EXECUTOR_RESULT_TIMEOUT", "42")
        seen = {}

        def fake_wait(reply_key, timeout):
            seen["timeout"] = timeout
            return None

        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(
                PgExecutionDispatcher, "_wait_for_result", side_effect=fake_wait
            ),
        ):
            # No explicit timeout arg → falls back to the env/default.
            PgExecutionDispatcher().dispatch(self._ctx())
        assert seen["timeout"] == 42

    def test_timeout_none_bad_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("EXECUTOR_RESULT_TIMEOUT", "not-an-int")
        seen = {}

        def fake_wait(reply_key, timeout):
            seen["timeout"] = timeout
            return None

        with (
            patch(f"{_MOD}.enqueue_task"),
            patch.object(
                PgExecutionDispatcher, "_wait_for_result", side_effect=fake_wait
            ),
        ):
            PgExecutionDispatcher().dispatch(self._ctx())  # must not raise
        assert seen["timeout"] == 3600  # _DEFAULT_TIMEOUT


def _ctx(org: str | None = "org1") -> MagicMock:
    c = MagicMock()
    c.executor_name = "legacy"
    c.run_id = "run-1"
    c.organization_id = org
    return c


def _gate(on: bool):
    s = MagicMock()
    s.PG_QUEUE_TRANSPORT_ENABLED = on
    return patch(f"{_MOD}.settings", s)


class TestResolveExecutorTransport:
    def test_master_gate_off_is_celery(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with _gate(False), patch(f"{_MOD}.check_feature_flag_status") as flag:
            assert resolve_executor_transport(_ctx()) is False
            flag.assert_not_called()  # gate off → Flipt never consulted

    def test_flipt_unavailable_is_celery(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "false")
        with _gate(True), patch(f"{_MOD}.check_feature_flag_status") as flag:
            assert resolve_executor_transport(_ctx()) is False
            flag.assert_not_called()

    def test_flag_true_is_pg_keyed_on_org(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with _gate(True), patch(
            f"{_MOD}.check_feature_flag_status", return_value=True
        ) as flag:
            assert resolve_executor_transport(_ctx("orgX")) is True
            assert flag.call_args.kwargs["entity_id"] == "orgX"
            # The single shared PG-queue flag (not a per-subsystem flag).
            assert flag.call_args.kwargs["flag_key"] == "pg_queue_enabled"

    def test_flag_false_is_celery(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with _gate(True), patch(
            f"{_MOD}.check_feature_flag_status", return_value=False
        ):
            assert resolve_executor_transport(_ctx()) is False

    def test_flipt_error_fails_closed_to_celery(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with _gate(True), patch(
            f"{_MOD}.check_feature_flag_status", side_effect=RuntimeError("down")
        ):
            assert resolve_executor_transport(_ctx()) is False


class TestRoutingZeroRegression:
    @staticmethod
    def _build():
        # Patch both sub-dispatchers at construction; the instances are captured
        # in __init__ so they remain mocked after the context exits.
        with (
            patch(f"{_MOD}.ExecutionDispatcher") as celery_cls,
            patch(f"{_MOD}.PgExecutionDispatcher") as pg_cls,
        ):
            dispatcher = RoutingExecutionDispatcher(celery_app="app")
        return dispatcher, celery_cls.return_value, pg_cls.return_value

    def test_gate_off_dispatch_uses_celery_only(self):
        dispatcher, celery, pg = self._build()
        with patch(f"{_MOD}.resolve_executor_transport", return_value=False):
            dispatcher.dispatch(_ctx())
        celery.dispatch.assert_called_once()
        pg.dispatch.assert_not_called()  # the zero-regression guarantee

    def test_gate_on_dispatch_uses_pg(self):
        dispatcher, celery, pg = self._build()
        with patch(f"{_MOD}.resolve_executor_transport", return_value=True):
            dispatcher.dispatch(_ctx())
        pg.dispatch.assert_called_once()
        celery.dispatch.assert_not_called()

    def test_async_and_callback_stay_celery_when_gate_off(self):
        """Zero-regression: gate off → async/callback delegate to Celery unchanged."""
        dispatcher, celery, pg = self._build()
        with patch(f"{_MOD}.resolve_executor_transport", return_value=False):
            dispatcher.dispatch_async(_ctx(), headers={"h": 1})
            dispatcher.dispatch_with_callback(_ctx(), on_success="s", on_error="e")
        celery.dispatch_async.assert_called_once()
        celery.dispatch_with_callback.assert_called_once()
        pg.dispatch_async.assert_not_called()
        pg.dispatch_with_callback.assert_not_called()

    def test_async_and_callback_route_to_pg_when_gated(self):
        """Gate on (③c) → async/callback take the PG self-chained path."""
        dispatcher, celery, pg = self._build()
        with patch(f"{_MOD}.resolve_executor_transport", return_value=True):
            dispatcher.dispatch_async(_ctx())
            dispatcher.dispatch_with_callback(
                _ctx(), on_success="s", on_error="e", task_id="t"
            )
        pg.dispatch_async.assert_called_once()
        pg.dispatch_with_callback.assert_called_once()
        assert "headers" not in pg.dispatch_with_callback.call_args.kwargs
        celery.dispatch_async.assert_not_called()
        celery.dispatch_with_callback.assert_not_called()


class TestPgAsyncCallbackWiring:
    """PG fire-and-forget + self-chained-callback enqueue shapes (``enqueue_task``
    mocked). Pins that the async path carries NO reply_key and the callback path
    carries the translated continuations + the tracking task_id.
    """

    @staticmethod
    def _ctx():
        c = MagicMock()
        c.executor_name = "legacy"
        c.run_id = "r"
        c.organization_id = "org9"
        c.to_dict.return_value = {"run_id": "r", "organization_id": "org9"}
        return c

    def test_dispatch_async_is_fire_and_forget(self):
        with patch(f"{_MOD}.enqueue_task") as enq:
            task_id = PgExecutionDispatcher().dispatch_async(self._ctx())
        kwargs = enq.call_args.kwargs
        assert kwargs["task_name"] == "execute_extraction"
        assert kwargs["queue"] == "celery_executor_legacy"
        assert kwargs["org_id"] == "org9"
        assert kwargs["task_id"] == task_id
        assert "reply_key" not in kwargs
        assert "on_success" not in kwargs

    def test_dispatch_with_callback_carries_continuations(self):
        on_s = MagicMock(
            task="ide_prompt_complete",
            args=(),
            kwargs={"callback_kwargs": {"room": "r1"}},
            options={"queue": "ide_callback"},
        )
        on_e = MagicMock(
            task="ide_prompt_error",
            args=(),
            kwargs={"callback_kwargs": {"room": "r1"}},
            options={"queue": "ide_callback"},
        )
        with patch(f"{_MOD}.enqueue_task") as enq:
            handle = PgExecutionDispatcher().dispatch_with_callback(
                self._ctx(), on_success=on_s, on_error=on_e, task_id="tid-7"
            )
        assert handle.id == "tid-7"  # call sites read .id off the handle
        kwargs = enq.call_args.kwargs
        assert kwargs["on_success"] == {
            "task_name": "ide_prompt_complete",
            "kwargs": {"callback_kwargs": {"room": "r1"}},
            "queue": "ide_callback",
        }
        assert kwargs["on_error"]["task_name"] == "ide_prompt_error"
        assert kwargs["task_id"] == "tid-7"
        assert "reply_key" not in kwargs
