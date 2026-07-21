"""Tests for WorkflowHelper._record_dispatch_handle — the post-dispatch
bookkeeping that records the transport's dispatch handle on the execution row.

Regression context: the PG path returns ``str(msg_id)`` (a bigint string). It
used to be written into ``WorkflowExecution.task_id`` (a UUIDField), raising
``ValueError`` on save → the broad post-dispatch handler swallowed it and
returned EXECUTING immediately, silently skipping the ``timeout`` sync-wait. The
fix routes the PG msg_id into its own ``queue_message_id`` (BigIntegerField) and
leaves ``task_id`` NULL on the PG path, so no bigint is ever forced into a UUID.

DB-free: ``WorkflowExecutionServiceHelper`` is mocked. These assert ROUTING
only (PG -> ``queue_message_id`` as int, Celery -> ``task_id``, malformed/empty
handle -> neither); the UUID-coercion crash and the timeout sync-wait are NOT
reproduced here (the helper is mocked). The defense-in-depth guarantee — a raise
during handle recording must not skip the wait loop — is covered separately in
``test_execute_workflow_async_wait.py``.
"""

from unittest.mock import patch

from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_MODEL = "workflow_manager.workflow_v2.execution.WorkflowExecution"

_HELPER = (
    "workflow_manager.workflow_v2.workflow_helper.WorkflowExecutionServiceHelper"
)
_EXEC = "exec-123"


class TestRecordDispatchHandle:
    def test_pg_handle_goes_to_queue_message_id_as_int_not_task_id(self):
        """The PG msg_id (bigint string) must be stored in queue_message_id as an
        int — never in the UUID task_id (the bug that crashed the wait loop)."""
        with patch(_HELPER) as helper:
            WorkflowHelper._record_dispatch_handle(
                execution_id=_EXEC,
                transport="pg_queue",
                dispatch_handle="1527",
                org_schema="org1",
                file_count=3,
            )
        helper.update_execution_queue_message_id.assert_called_once_with(
            execution_id=_EXEC, queue_message_id=1527
        )
        assert isinstance(
            helper.update_execution_queue_message_id.call_args.kwargs[
                "queue_message_id"
            ],
            int,
        )
        helper.update_execution_task.assert_not_called()  # task_id stays NULL

    def test_celery_handle_goes_to_task_id_not_queue_message_id(self):
        with patch(_HELPER) as helper:
            WorkflowHelper._record_dispatch_handle(
                execution_id=_EXEC,
                transport="celery",
                dispatch_handle="b1b2c3d4-0000-0000-0000-000000000000",
                org_schema="org1",
                file_count=1,
            )
        helper.update_execution_task.assert_called_once_with(
            execution_id=_EXEC, task_id="b1b2c3d4-0000-0000-0000-000000000000"
        )
        helper.update_execution_queue_message_id.assert_not_called()

    def test_empty_handle_records_nothing(self):
        with patch(_HELPER) as helper:
            WorkflowHelper._record_dispatch_handle(
                execution_id=_EXEC,
                transport="celery",
                dispatch_handle=None,
                org_schema="org1",
                file_count=0,
            )
        helper.update_execution_task.assert_not_called()
        helper.update_execution_queue_message_id.assert_not_called()

    def test_non_numeric_pg_handle_records_nothing(self):
        """A malformed PG handle (not a bigint) must be parsed defensively — no
        ValueError out of the helper, and nothing recorded. Today this can't
        happen (``_dispatch_orchestrator_task`` always returns ``str(msg_id)``),
        so this pins the contract against a future handle-format change."""
        with patch(_HELPER) as helper:
            WorkflowHelper._record_dispatch_handle(
                execution_id=_EXEC,
                transport="pg_queue",
                dispatch_handle="not-a-number",
                org_schema="org1",
                file_count=1,
            )
        helper.update_execution_queue_message_id.assert_not_called()
        helper.update_execution_task.assert_not_called()


class TestUpdateQueueMessageIdWriteShape:
    """``update_execution_queue_message_id`` must persist the PG handle with a
    DB-side single-column queryset ``.update()`` — NOT ``execution.save()``.

    Regression: ``save()`` (even with ``update_fields``) re-runs the model's
    ``_handle_execution_cache()``, which republishes this method's stale in-memory
    ``status`` to the Redis execution cache. If that write lands after the worker
    has advanced status, it reverts the cache to the stale value with no later
    corrector and the API-deployment sync-poll blocks to its full timeout. The
    codebase already uses the queryset-``.update()`` pattern for the same reason
    in ``_set_result_acknowledge``; this pins it for the marker write too.
    """

    def test_write_uses_queryset_update_not_save(self):
        with patch(_MODEL) as model:
            model.objects.filter.return_value.update.return_value = 1
            WorkflowExecutionServiceHelper.update_execution_queue_message_id(
                execution_id="exec-1", queue_message_id=1527
            )
        # queryset .update() on ONLY the handle column, keyed by pk...
        model.objects.filter.assert_called_once_with(pk="exec-1")
        model.objects.filter.return_value.update.assert_called_once_with(
            queue_message_id=1527
        )
        # ...and never the hydrate-then-save() path that republishes the cache.
        model.objects.get.assert_not_called()

    def test_none_handle_is_a_noop(self):
        with patch(_MODEL) as model:
            WorkflowExecutionServiceHelper.update_execution_queue_message_id(
                execution_id="exec-1", queue_message_id=None
            )
        model.objects.filter.assert_not_called()

    def test_missing_execution_does_not_raise(self):
        """update() returning 0 (row gone) is logged, not raised."""
        with patch(_MODEL) as model:
            model.objects.filter.return_value.update.return_value = 0
            # must not raise
            WorkflowExecutionServiceHelper.update_execution_queue_message_id(
                execution_id="missing", queue_message_id=99
            )
        model.objects.filter.return_value.update.assert_called_once_with(
            queue_message_id=99
        )
