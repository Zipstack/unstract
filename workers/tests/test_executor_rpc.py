"""Tests for the workers-side executor-RPC transport routing (Phase 9, ③b-2).

DB-free: the env gate / Flipt / the enqueue + poll halves are mocked. Pins the
gate's fail-closed matrix and — the load-bearing zero-regression property — that
with the gate off ``RoutingExecutionDispatcher`` delegates EVERY mode to the
unchanged Celery ``ExecutionDispatcher`` and never touches the PG path. Mirrors
``backend/pg_queue/tests/test_executor_rpc.py`` (the backend twin) adapted to the
worker primitives: an env master-gate instead of a Django setting, and the result
row is a plain ``dict`` (``PgResultBackend``) instead of a Django model.
"""

from unittest.mock import MagicMock, patch

import pytest
from queue_backend.pg_queue.executor_rpc import (
    PgExecutionDispatcher,
    RoutingExecutionDispatcher,
    resolve_executor_transport,
)
from unstract.core.execution_dispatch import DispatchHandle, signature_to_continuation

_MOD = "queue_backend.pg_queue.executor_rpc"


def _completed(result: dict) -> dict:
    return {"status": "completed", "result": result, "error": ""}


def _ok_result() -> dict:
    return {"success": True, "data": {"x": 1}, "metadata": {}, "error": None}


class TestPgExecutionDispatcherDispatch:
    """The load-bearing contract: never raises; timeout/failure → failure result.

    DB-free — the ``_enqueue`` and ``_wait_for_result`` halves are mocked.
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
        with patch.object(
            PgExecutionDispatcher, "_enqueue", side_effect=RuntimeError("db down")
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert "RuntimeError" in res.error

    def test_wait_failure_returns_failure_not_raise(self):
        with (
            patch.object(PgExecutionDispatcher, "_enqueue"),
            patch.object(
                PgExecutionDispatcher,
                "_wait_for_result",
                side_effect=RuntimeError("conn died"),
            ),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert "RuntimeError" in res.error

    def test_timeout_returns_failure(self):
        with (
            patch.object(PgExecutionDispatcher, "_enqueue"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=None),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=3)
        assert res.success is False
        assert "within 3s" in res.error

    def test_completed_row_returns_result(self):
        with (
            patch.object(PgExecutionDispatcher, "_enqueue"),
            patch.object(
                PgExecutionDispatcher,
                "_wait_for_result",
                return_value=_completed(_ok_result()),
            ),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is True

    def test_failed_row_returns_error(self):
        row = {"status": "failed", "result": None, "error": "boom"}
        with (
            patch.object(PgExecutionDispatcher, "_enqueue"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=row),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert res.error == "boom"

    def test_failed_row_empty_error_falls_back(self):
        row = {"status": "failed", "result": None, "error": ""}
        with (
            patch.object(PgExecutionDispatcher, "_enqueue"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=row),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False
        assert "executor task failed" in res.error

    def test_completed_but_result_none_is_failure(self):
        row = {"status": "completed", "result": None, "error": ""}
        with (
            patch.object(PgExecutionDispatcher, "_enqueue"),
            patch.object(PgExecutionDispatcher, "_wait_for_result", return_value=row),
        ):
            res = PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        assert res.success is False

    def test_malformed_completed_row_is_failure_not_raise(self):
        with (
            patch.object(PgExecutionDispatcher, "_enqueue"),
            patch.object(
                PgExecutionDispatcher,
                "_wait_for_result",
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
            patch.object(PgExecutionDispatcher, "_enqueue"),
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
            patch.object(PgExecutionDispatcher, "_enqueue"),
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


class TestResolveExecutorTransport:
    def test_master_gate_off_is_celery(self, monkeypatch):
        monkeypatch.delenv("PG_QUEUE_TRANSPORT_ENABLED", raising=False)
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(f"{_MOD}.check_feature_flag_status") as flag:
            assert resolve_executor_transport(_ctx()) is False
            flag.assert_not_called()  # gate off → Flipt never consulted

    def test_flipt_unavailable_is_celery(self, monkeypatch):
        monkeypatch.setenv("PG_QUEUE_TRANSPORT_ENABLED", "true")
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "false")
        with patch(f"{_MOD}.check_feature_flag_status") as flag:
            assert resolve_executor_transport(_ctx()) is False
            flag.assert_not_called()

    def test_flag_true_is_pg_keyed_on_org(self, monkeypatch):
        monkeypatch.setenv("PG_QUEUE_TRANSPORT_ENABLED", "true")
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(
            f"{_MOD}.check_feature_flag_status", return_value=True
        ) as flag:
            assert resolve_executor_transport(_ctx("orgX")) is True
            assert flag.call_args.kwargs["entity_id"] == "orgX"
            # The single shared PG-queue flag (not a per-subsystem flag).
            assert flag.call_args.kwargs["flag_key"] == "pg_queue_enabled"

    def test_flag_false_is_celery(self, monkeypatch):
        monkeypatch.setenv("PG_QUEUE_TRANSPORT_ENABLED", "true")
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(f"{_MOD}.check_feature_flag_status", return_value=False):
            assert resolve_executor_transport(_ctx()) is False

    def test_flipt_error_fails_closed_to_celery(self, monkeypatch):
        monkeypatch.setenv("PG_QUEUE_TRANSPORT_ENABLED", "true")
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(
            f"{_MOD}.check_feature_flag_status", side_effect=RuntimeError("down")
        ):
            assert resolve_executor_transport(_ctx()) is False

    def test_org_less_context_buckets_on_run_id(self, monkeypatch):
        """No org → entity_id falls back to run_id and org is absent from context.

        Guards the org-less bucketing so cross-org/run-only contexts resolve
        deterministically instead of shipping a bogus "None" org.
        """
        monkeypatch.setenv("PG_QUEUE_TRANSPORT_ENABLED", "true")
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(
            f"{_MOD}.check_feature_flag_status", return_value=True
        ) as flag:
            assert resolve_executor_transport(_ctx(org=None)) is True
        assert flag.call_args.kwargs["entity_id"] == "run-1"
        assert "organization_id" not in flag.call_args.kwargs["context"]


class TestPgExecutionDispatcherEnqueueWiring:
    """The actual PG-transport wiring: queue name, payload shape, org_id.

    These are the *only* routing/identity carried on the PG path (Celery headers
    are dropped), so a bug here misroutes or breaks org-fairness. ``to_payload``
    runs for real; only ``PgQueueClient`` and the wait are mocked.
    """

    @staticmethod
    def _ctx():
        c = MagicMock()
        c.executor_name = "legacy"
        c.run_id = "r"
        c.organization_id = "org9"
        c.to_dict.return_value = {"run_id": "r"}
        return c

    def test_enqueue_sends_queue_payload_and_org(self):
        client = MagicMock()
        client.__enter__.return_value = client  # `with PgQueueClient() as c` → c is client
        with (
            patch(f"{_MOD}.PgQueueClient", return_value=client),
            patch.object(
                PgExecutionDispatcher,
                "_wait_for_result",
                return_value=_completed(_ok_result()),
            ),
        ):
            PgExecutionDispatcher().dispatch(self._ctx(), timeout=5)
        client.send.assert_called_once()
        args, kwargs = client.send.call_args
        queue_arg, payload_arg = args[0], args[1]
        assert queue_arg == "celery_executor_legacy"
        assert kwargs["org_id"] == "org9"
        assert payload_arg["task_name"] == "execute_extraction"
        assert payload_arg["args"] == [{"run_id": "r"}]
        assert payload_arg["reply_key"]  # request-reply marker present (a uuid)


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

    def test_gate_off_forwards_timeout_and_headers_to_celery(self):
        """Zero-regression: gate off → Celery gets timeout AND headers unchanged."""
        dispatcher, celery, pg = self._build()
        ctx = _ctx()
        hdrs = {"x-fairness-key": {"org_id": "o"}}
        with patch(f"{_MOD}.resolve_executor_transport", return_value=False):
            dispatcher.dispatch(ctx, timeout=9, headers=hdrs)
        celery.dispatch.assert_called_once_with(ctx, timeout=9, headers=hdrs)
        pg.dispatch.assert_not_called()  # the zero-regression guarantee

    def test_gate_on_passes_timeout_to_pg_and_drops_headers(self):
        """Gate on → PG gets the timeout but NOT the Celery headers (intentional)."""
        dispatcher, celery, pg = self._build()
        ctx = _ctx()
        with patch(f"{_MOD}.resolve_executor_transport", return_value=True):
            dispatcher.dispatch(ctx, timeout=7, headers={"x-fairness-key": {"o": 1}})
        pg.dispatch.assert_called_once_with(ctx, timeout=7)
        assert "headers" not in pg.dispatch.call_args.kwargs
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
        # PG carries callbacks in the payload, not Celery headers → no header leak.
        assert "headers" not in pg.dispatch_with_callback.call_args.kwargs
        celery.dispatch_async.assert_not_called()
        celery.dispatch_with_callback.assert_not_called()


class TestPgAsyncCallbackWiring:
    """PG fire-and-forget + self-chained-callback enqueue shapes.

    ``to_payload`` runs for real; only ``PgQueueClient`` is mocked. Pins that the
    async path carries NO reply_key (it must not block a consumer) and the callback
    path carries the translated continuations + the tracking task_id.
    """

    @staticmethod
    def _ctx():
        c = MagicMock()
        c.executor_name = "legacy"
        c.run_id = "r"
        c.organization_id = "org9"
        c.to_dict.return_value = {"run_id": "r", "organization_id": "org9"}
        return c

    @staticmethod
    def _client():
        client = MagicMock()
        client.__enter__.return_value = client
        return client

    def test_dispatch_async_is_fire_and_forget(self):
        client = self._client()
        with patch(f"{_MOD}.PgQueueClient", return_value=client):
            task_id = PgExecutionDispatcher().dispatch_async(self._ctx())
        client.send.assert_called_once()
        queue_arg, payload_arg = client.send.call_args.args[:2]
        assert queue_arg == "celery_executor_legacy"
        assert client.send.call_args.kwargs["org_id"] == "org9"
        assert payload_arg["task_name"] == "execute_extraction"
        assert payload_arg["task_id"] == task_id
        # No reply_key (would make a consumer try to store a reply) and no callback.
        assert "reply_key" not in payload_arg
        assert "on_success" not in payload_arg
        assert "on_error" not in payload_arg

    def test_dispatch_with_callback_carries_continuations(self):
        client = self._client()
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
        with patch(f"{_MOD}.PgQueueClient", return_value=client):
            handle = PgExecutionDispatcher().dispatch_with_callback(
                self._ctx(), on_success=on_s, on_error=on_e, task_id="tid-7"
            )
        assert handle.id == "tid-7"  # call sites read .id off the handle
        payload_arg = client.send.call_args.args[1]
        assert payload_arg["on_success"] == {
            "task_name": "ide_prompt_complete",
            "kwargs": {"callback_kwargs": {"room": "r1"}},
            "queue": "ide_callback",
        }
        assert payload_arg["on_error"]["task_name"] == "ide_prompt_error"
        assert payload_arg["task_id"] == "tid-7"
        assert "reply_key" not in payload_arg  # callback, not request-reply

    def test_dispatch_with_callback_defaults_task_id(self):
        client = self._client()
        with patch(f"{_MOD}.PgQueueClient", return_value=client):
            handle = PgExecutionDispatcher().dispatch_with_callback(self._ctx())
        # No task_id passed → a uuid is generated and echoed on the handle + payload.
        assert handle.id
        assert client.send.call_args.args[1]["task_id"] == handle.id


class TestSharedDispatchHelpers:
    """The transport-agnostic helpers lifted to ``unstract.core`` (shared by the
    backend + workers executor-RPC mirrors). Tested once here, not per-mirror.
    """

    def test_signature_none_passes_through(self):
        assert signature_to_continuation(None) is None

    def test_signature_translates_task_kwargs_and_queue(self):
        sig = MagicMock(
            task="ide_prompt_complete",
            args=(),  # a real kwargs-only Celery Signature has empty .args
            kwargs={"callback_kwargs": {"room": "r1"}},
            options={"queue": "ide_callback"},
        )
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
        sig = MagicMock(
            task="ide_prompt_complete",
            args=("pos",),
            kwargs={},
            options={"queue": "ide_callback"},
        )
        with pytest.raises(ValueError, match="positional args"):
            signature_to_continuation(sig)

    def test_dispatch_handle_exposes_only_id(self):
        handle = DispatchHandle("tid-1")
        assert handle.id == "tid-1"
        # __slots__ → no stray attributes (callers must not poke at .get()/.result).
        with pytest.raises(AttributeError):
            handle.result = 1  # type: ignore[attr-defined]
