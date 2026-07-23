"""PG at-least-once duplicate guard for the aggregating callback (H1).

The callback (``process_batch_callback`` / ``_api``) re-runs status update,
subscription-usage billing and customer webhooks wholesale; on the PG path it can
be REDELIVERED (the ``PgQueueClient.send`` commit-retry double-enqueue, an
idle-reaped ack, a vt overrun). When a prior delivery already COMPLETED the
execution, the redelivery must SKIP its side effects. The guard is PG-gated by the
``_pg_transport`` marker the barrier stamps on the PG dispatch, so the Celery
``.link`` path (no redelivery) is a strict no-op.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import callback.tasks as cb
from queue_backend.pg_barrier import PG_TRANSPORT_CALLBACK_KWARG
from unstract.core.data_models import ExecutionStatus


class TestCallbackAlreadyRan:
    """The pure predicate: COMPLETED only (a status a prior callback alone sets)."""

    def test_completed_is_true(self):
        assert cb._callback_already_ran(ExecutionStatus.COMPLETED.value) is True

    @pytest.mark.parametrize(
        "status",
        [
            ExecutionStatus.EXECUTING.value,
            ExecutionStatus.PENDING.value,
            # ERROR / STOPPED can be set by OTHER paths → NOT "a prior callback ran".
            ExecutionStatus.ERROR.value,
            ExecutionStatus.STOPPED.value,
            None,
        ],
    )
    def test_non_completed_is_false(self, status):
        assert cb._callback_already_ran(status) is False


class TestCoreCallbackGuard:
    """``_process_batch_callback_core`` short-circuits a PG duplicate before any
    side effect (using the status the context already carries), and only on PG.
    """

    def _context(self, status):
        ctx = MagicMock()
        ctx.organization_id = "org-1"
        ctx.api_client = MagicMock()
        ctx.execution_id = "e1"
        ctx.execution_status = status
        return ctx

    def _run(self, *, is_pg: bool, status: str):
        kwargs = {"execution_id": "e1"}
        if is_pg:
            kwargs[PG_TRANSPORT_CALLBACK_KWARG] = True
        extract = MagicMock(return_value=self._context(status))
        with (
            patch.object(cb, "_initialize_performance_managers"),
            patch.object(cb, "_extract_callback_parameters", extract),
            patch.object(cb, "_determine_execution_status_unified") as determine,
        ):
            determine.side_effect = AssertionError("side effects must not run")
            out = cb._process_batch_callback_core(MagicMock(), [], **kwargs)
        return out, extract, determine

    def test_pg_duplicate_skips_side_effects(self):
        out, extract, determine = self._run(
            is_pg=True, status=ExecutionStatus.COMPLETED.value
        )
        assert out["status"] == "skipped_duplicate_callback"
        assert out["duplicate_callback_skipped"] is True
        determine.assert_not_called()  # no status update / billing / webhooks
        # The marker must be popped BEFORE extraction — never leak into the context.
        assert PG_TRANSPORT_CALLBACK_KWARG not in extract.call_args.args[2]

    def test_pg_non_completed_proceeds(self):
        # Not COMPLETED → the guard lets the callback run (reaches the side-effect
        # step, stubbed to raise as the proof-of-reach).
        with pytest.raises(AssertionError, match="side effects must not run"):
            self._run(is_pg=True, status=ExecutionStatus.EXECUTING.value)

    def test_pg_error_status_proceeds(self):
        # ERROR is excluded (may be external) → the first callback must still run.
        with pytest.raises(AssertionError, match="side effects must not run"):
            self._run(is_pg=True, status=ExecutionStatus.ERROR.value)

    def test_celery_never_skips(self):
        # No marker → guard skipped entirely; the callback proceeds even on a
        # COMPLETED status — proving zero Celery regression.
        with pytest.raises(AssertionError, match="side effects must not run"):
            self._run(is_pg=False, status=ExecutionStatus.COMPLETED.value)


class TestApiCallbackGuard:
    """``process_batch_callback_api`` short-circuits a PG duplicate using the
    execution status it already fetches (no extra round-trip).
    """

    def _run(self, *, is_pg: bool, status: str):
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
            patch.object(cb, "_determine_execution_status_unified") as determine,
        ):
            determine.side_effect = AssertionError("side effects must not run")
            out = cb.process_batch_callback_api(task, [], **kwargs)
        return out, determine

    def test_pg_duplicate_skips_side_effects(self):
        out, determine = self._run(is_pg=True, status=ExecutionStatus.COMPLETED.value)
        assert out["status"] == "skipped_duplicate_callback"
        determine.assert_not_called()

    def test_pg_non_completed_proceeds(self):
        with pytest.raises(AssertionError, match="side effects must not run"):
            self._run(is_pg=True, status=ExecutionStatus.EXECUTING.value)

    def test_celery_never_skips(self):
        with pytest.raises(AssertionError, match="side effects must not run"):
            self._run(is_pg=False, status=ExecutionStatus.COMPLETED.value)
