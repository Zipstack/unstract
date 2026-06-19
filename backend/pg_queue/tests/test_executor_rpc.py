"""Tests for the executor-RPC transport routing (Phase 9).

DB-free: settings / Flipt / the sub-dispatchers are mocked. Pins the gate's
fail-closed matrix and — the load-bearing zero-regression property — that with
the gate off ``RoutingExecutionDispatcher`` delegates EVERY mode to the unchanged
Celery ``ExecutionDispatcher`` and never touches the PG path.
"""

from unittest.mock import MagicMock, patch

from pg_queue.executor_rpc import (
    RoutingExecutionDispatcher,
    resolve_executor_transport,
)

_MOD = "pg_queue.executor_rpc"


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

    def test_async_and_callback_always_celery(self):
        """The callback/async path stays on Celery regardless of the gate (a later slice)."""
        dispatcher, celery, pg = self._build()
        dispatcher.dispatch_async(_ctx())
        dispatcher.dispatch_with_callback(_ctx(), on_success=None)
        celery.dispatch_async.assert_called_once()
        celery.dispatch_with_callback.assert_called_once()
        pg.dispatch.assert_not_called()
