"""Tests for WorkflowHelper._record_dispatch_handle — the post-dispatch
bookkeeping that records the transport's dispatch handle on the execution row.

Regression context: the PG path returns ``str(msg_id)`` (a bigint string). It
used to be written into ``WorkflowExecution.task_id`` (a UUIDField), raising
``ValueError`` on save → the broad post-dispatch handler swallowed it and
returned EXECUTING immediately, silently skipping the ``timeout`` sync-wait. The
fix routes the PG msg_id into its own ``queue_message_id`` (BigIntegerField) and
leaves ``task_id`` NULL on the PG path, so no bigint is ever forced into a UUID.

DB-free: ``WorkflowExecutionServiceHelper`` is mocked.
"""

from unittest.mock import patch

from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

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
