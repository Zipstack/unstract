"""PG at-least-once duplicate guard for the aggregating callback (H1).

The callback (``process_batch_callback`` / ``_api``) re-runs status update,
subscription-usage billing and customer webhooks wholesale; on the PG path it can
be REDELIVERED (the ``PgQueueClient.send`` commit-retry double-enqueue, an
idle-reaped ack, a vt overrun). When a prior delivery already finalized the
execution, the redelivery must SKIP its side effects. The guard is PG-gated by the
``_pg_transport`` marker the barrier stamps on the PG dispatch, so the Celery
``.link`` path (no redelivery) is a strict no-op.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import callback.tasks as cb
from queue_backend.pg_barrier import PG_TRANSPORT_CALLBACK_KWARG
from unstract.core.data_models import ExecutionStatus


def _exec_response(status: str, *, success: bool = True):
    return MagicMock(success=success, data={"execution": {"status": status}})


class TestExecutionAlreadyFinalized:
    def test_terminal_is_true(self):
        api = MagicMock()
        api.get_workflow_execution.return_value = _exec_response(
            ExecutionStatus.COMPLETED.value
        )
        assert cb._pg_execution_already_finalized(api, "e1") is True

    def test_non_terminal_is_false(self):
        api = MagicMock()
        api.get_workflow_execution.return_value = _exec_response(
            ExecutionStatus.EXECUTING.value
        )
        assert cb._pg_execution_already_finalized(api, "e1") is False

    def test_unsuccessful_fetch_proceeds(self):
        api = MagicMock()
        api.get_workflow_execution.return_value = _exec_response("x", success=False)
        assert cb._pg_execution_already_finalized(api, "e1") is False

    def test_fetch_error_proceeds_not_raises(self):
        # Best-effort: a fetch failure must proceed (tolerable duplicate), never
        # raise (which would fail the callback) or wrongly skip a real callback.
        api = MagicMock()
        api.get_workflow_execution.side_effect = RuntimeError("api down")
        assert cb._pg_execution_already_finalized(api, "e1") is False


class TestCoreCallbackGuard:
    """``_process_batch_callback_core`` short-circuits a PG duplicate before any
    side effect, and only on the PG path.
    """

    def _context(self):
        ctx = MagicMock()
        ctx.organization_id = "org-1"
        ctx.api_client = MagicMock()
        ctx.execution_id = "e1"
        return ctx

    def _run(self, *, is_pg: bool, terminal: bool):
        kwargs = {"execution_id": "e1"}
        if is_pg:
            kwargs[PG_TRANSPORT_CALLBACK_KWARG] = True
        with (
            patch.object(cb, "_initialize_performance_managers"),
            patch.object(cb, "_extract_callback_parameters", return_value=self._context()),
            patch.object(
                cb, "_pg_execution_already_finalized", return_value=terminal
            ) as finalized,
            patch.object(cb, "_determine_execution_status_unified") as determine,
        ):
            determine.side_effect = AssertionError("side effects must not run")
            out = cb._process_batch_callback_core(MagicMock(), [], **kwargs)
        return out, finalized, determine

    def test_pg_duplicate_skips_side_effects(self):
        out, finalized, determine = self._run(is_pg=True, terminal=True)
        assert out["status"] == "skipped_duplicate_callback"
        assert out["duplicate_callback_skipped"] is True
        finalized.assert_called_once()
        determine.assert_not_called()  # no status update / billing / webhooks

    def test_pg_non_terminal_proceeds(self):
        # Not yet finalized → the guard must let the callback run (reaches the
        # side-effect step, which we stubbed to raise as the proof-of-reach).
        import pytest

        with pytest.raises(AssertionError, match="side effects must not run"):
            self._run(is_pg=True, terminal=False)

    def test_celery_never_checks_or_skips(self):
        # No marker → the guard is skipped entirely (finalized never called) and
        # the callback proceeds — proving zero Celery regression.
        import pytest

        with pytest.raises(AssertionError, match="side effects must not run"):
            _, finalized, _ = self._run(is_pg=False, terminal=True)


class TestApiCallbackGuard:
    """``process_batch_callback_api`` short-circuits a PG duplicate using the
    execution status it already fetches (no extra round-trip).
    """

    def _run(self, *, is_pg: bool, terminal: bool):
        status = (
            ExecutionStatus.COMPLETED.value if terminal else ExecutionStatus.EXECUTING.value
        )
        api = MagicMock()
        api.get_workflow_execution.return_value = MagicMock(
            success=True,
            data={
                "execution": {"status": status, "workflow_id": "wf"},
                "workflow": {"id": "wf"},
            },
        )
        kwargs = {"execution_id": "e1", "organization_id": "org-1", "pipeline_id": "p"}
        if is_pg:
            kwargs[PG_TRANSPORT_CALLBACK_KWARG] = True
        task = MagicMock()
        task.request.id = "t1"
        with (
            patch.object(cb, "create_api_client", return_value=api),
            patch.object(
                cb, "_determine_execution_status_unified"
            ) as determine,
        ):
            determine.side_effect = AssertionError("side effects must not run")
            out = cb.process_batch_callback_api(task, [], **kwargs)
        return out, determine

    def test_pg_duplicate_skips_side_effects(self):
        out, determine = self._run(is_pg=True, terminal=True)
        assert out["status"] == "skipped_duplicate_callback"
        determine.assert_not_called()

    def test_celery_never_skips(self):
        import pytest

        with pytest.raises(AssertionError, match="side effects must not run"):
            self._run(is_pg=False, terminal=True)
