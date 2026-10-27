"""UN-4177 — the API sync wait must not pin a DB connection while it sleeps.

Django holds one connection per request, and behind pgbouncer's session pool
that is one Postgres server connection for as long as the request lives. The
sync wait in ``execute_workflow_async`` (and ``wait_for_execution``) used to
sleep-poll for up to the API timeout with that connection still open, so every
waiting API request held a slot doing nothing.

These tests pin that the connection is closed before each sleep, that nothing
changes on the async path (``timeout=-1``), and that an open atomic block is
never closed under the caller.

The unit tests are DB-free: the module's ``connections``, the model, the
context and ``time`` are mocked. ``TestReleaseAgainstRealConnection`` needs a
real Postgres, so the conftest marks it ``integration``.
"""

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from workflow_manager.workflow_v2.dto import ExecutionResponse
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_MOD = "workflow_manager.workflow_v2.workflow_helper"


def _open_conn(alias: str = "default") -> MagicMock:
    return MagicMock(alias=alias, in_atomic_block=False, autocommit=True)


@pytest.fixture
def db_connections():
    with patch(f"{_MOD}.connections") as conns:
        conns.all.return_value = [_open_conn()]
        yield conns


@pytest.fixture
def db_connection(db_connections):
    """The single open ``default`` connection; ``.close`` is the release call."""
    conn = db_connections.all.return_value[0]
    conn.close = conn.close_if_unusable_or_obsolete
    return conn


@pytest.fixture
def async_deps():
    """Everything ``execute_workflow_async`` touches besides the connection."""
    exec_row = MagicMock(status=ExecutionStatus.EXECUTING.value)
    with (
        patch(f"{_MOD}.UserContext") as user_ctx,
        patch(f"{_MOD}.StateStore") as state_store,
        patch(f"{_MOD}.time") as time_mod,
        patch(f"{_MOD}.WorkflowExecution") as wf_exec,
        patch(f"{_MOD}.WorkflowExecutionServiceHelper"),
        patch(f"{_MOD}.ResultCacheUtils"),
        patch.object(WorkflowHelper, "_dispatch_orchestrator_task", return_value="1"),
        patch.object(WorkflowHelper, "_record_dispatch_handle"),
        patch.object(WorkflowHelper, "set_result_acknowledge"),
        patch.object(WorkflowHelper, "_get_execution_status") as get_status,
    ):
        user_ctx.get_organization_identifier.return_value = "org1"
        state_store.get.return_value = None
        wf_exec.objects.get.return_value = exec_row
        yield time_mod, get_status


def _run_async(timeout: int) -> ExecutionResponse:
    return WorkflowHelper.execute_workflow_async(
        workflow_id="wf-1",
        execution_id="exec-1",
        hash_values_of_files={},
        timeout=timeout,
    )


class TestExecuteWorkflowAsyncWait:
    def test_connection_closed_before_every_sleep(self, db_connection, async_deps):
        time_mod, get_status = async_deps
        get_status.side_effect = [
            ExecutionStatus.EXECUTING,
            ExecutionStatus.EXECUTING,
            ExecutionStatus.COMPLETED,
        ]
        order = MagicMock()
        order.attach_mock(db_connection.close, "close")
        order.attach_mock(time_mod.sleep, "sleep")

        response = _run_async(timeout=10)

        assert response.execution_status == ExecutionStatus.COMPLETED
        # Close precedes each sleep — including the ones after a status read,
        # since a cache miss there reopens the connection.
        assert order.mock_calls == [call.close(), call.sleep(2)] * 3

    def test_failing_release_does_not_skip_the_wait(self, db_connection, async_deps):
        _, get_status = async_deps
        db_connection.close_if_unusable_or_obsolete.side_effect = RuntimeError("boom")
        get_status.side_effect = [ExecutionStatus.EXECUTING, ExecutionStatus.COMPLETED]

        response = _run_async(timeout=10)

        assert get_status.call_count == 2
        assert response.execution_status == ExecutionStatus.COMPLETED

    def test_async_path_leaves_connection_alone(self, db_connection, async_deps):
        time_mod, get_status = async_deps

        _run_async(timeout=-1)

        db_connection.close.assert_not_called()
        time_mod.sleep.assert_not_called()
        get_status.assert_not_called()

    def test_already_completed_skips_release(self, db_connection, async_deps):
        _, get_status = async_deps
        with patch(f"{_MOD}.WorkflowExecution") as wf_exec:
            wf_exec.objects.get.return_value = MagicMock(
                status=ExecutionStatus.COMPLETED.value
            )
            _run_async(timeout=10)

        db_connection.close.assert_not_called()
        get_status.assert_not_called()

    def test_atomic_block_is_never_closed(self, db_connection, async_deps):
        _, get_status = async_deps
        db_connection.in_atomic_block = True
        get_status.return_value = ExecutionStatus.COMPLETED

        response = _run_async(timeout=10)

        db_connection.close.assert_not_called()
        # The wait itself still runs normally.
        assert get_status.called
        assert response.execution_status == ExecutionStatus.COMPLETED


class TestWaitForExecution:
    def test_connection_closed_before_every_sleep(self, db_connection):
        result = ExecutionResponse("wf-1", "exec-1", ExecutionStatus.EXECUTING.value)
        with (
            patch(f"{_MOD}.time") as time_mod,
            patch.object(
                WorkflowHelper,
                "_get_execution_status",
                side_effect=[ExecutionStatus.EXECUTING, ExecutionStatus.COMPLETED],
            ),
        ):
            order = MagicMock()
            order.attach_mock(db_connection.close, "close")
            order.attach_mock(time_mod.sleep, "sleep")

            WorkflowHelper.wait_for_execution(result, timeout=10)

        assert order.mock_calls == [call.close(), call.sleep(2)] * 2
        assert result.execution_status == ExecutionStatus.COMPLETED

    def test_no_timeout_leaves_connection_alone(self, db_connection):
        result = ExecutionResponse("wf-1", "exec-1", ExecutionStatus.EXECUTING.value)

        WorkflowHelper.wait_for_execution(result, timeout=None)

        db_connection.close.assert_not_called()


class TestReleaseDbConnection:
    def test_releases_outside_a_transaction(self, db_connection):
        WorkflowHelper._release_db_connection()
        db_connection.close_if_unusable_or_obsolete.assert_called_once_with()

    def test_skips_inside_atomic(self, db_connection):
        db_connection.in_atomic_block = True
        WorkflowHelper._release_db_connection()
        db_connection.close_if_unusable_or_obsolete.assert_not_called()

    def test_skips_when_autocommit_is_off(self, db_connection):
        # Pending writes outside an atomic block: closing would roll them back.
        db_connection.autocommit = False
        WorkflowHelper._release_db_connection()
        db_connection.close_if_unusable_or_obsolete.assert_not_called()

    def test_skips_a_closed_connection_without_reconnecting(self, db_connection):
        db_connection.connection = None
        WorkflowHelper._release_db_connection()
        db_connection.close_if_unusable_or_obsolete.assert_not_called()

    def test_a_failing_release_does_not_raise(self, db_connection):
        db_connection.close_if_unusable_or_obsolete.side_effect = RuntimeError("boom")
        WorkflowHelper._release_db_connection()  # must not propagate

    @pytest.mark.parametrize(
        ("quiet", "level"), [(False, logging.WARNING), (True, logging.DEBUG)]
    )
    def test_skip_is_logged_loudly_only_when_not_quiet(self, db_connection, quiet, level):
        db_connection.in_atomic_block = True
        with patch(f"{_MOD}.logger") as log:
            WorkflowHelper._release_db_connection(quiet=quiet)
        assert log.log.call_args.args[0] == level


class TestReleaseLogsOncePerWait:
    def test_only_the_first_poll_is_loud(self, db_connection, async_deps):
        _, get_status = async_deps
        get_status.side_effect = [ExecutionStatus.EXECUTING] * 2 + [
            ExecutionStatus.COMPLETED
        ]
        with patch.object(WorkflowHelper, "_release_db_connection") as release:
            _run_async(timeout=10)
        assert release.call_args_list == [
            call(quiet=False),
            call(quiet=True),
            call(quiet=True),
        ]

    def test_wait_for_execution_only_the_first_poll_is_loud(self):
        result = ExecutionResponse("wf-1", "exec-1", ExecutionStatus.EXECUTING.value)
        with (
            patch(f"{_MOD}.time"),
            patch.object(
                WorkflowHelper,
                "_get_execution_status",
                side_effect=[ExecutionStatus.EXECUTING, ExecutionStatus.COMPLETED],
            ),
            patch.object(WorkflowHelper, "_release_db_connection") as release,
        ):
            WorkflowHelper.wait_for_execution(result, timeout=10)
        assert release.call_args_list == [call(quiet=False), call(quiet=True)]

    def test_releases_every_initialized_alias(self, db_connections):
        default, other = _open_conn("default"), _open_conn("other")
        db_connections.all.return_value = [default, other]

        WorkflowHelper._release_db_connection()

        db_connections.all.assert_called_once_with(initialized_only=True)
        default.close_if_unusable_or_obsolete.assert_called_once_with()
        other.close_if_unusable_or_obsolete.assert_called_once_with()


@pytest.mark.django_db(transaction=True)
class TestReleaseAgainstRealConnection:
    """The mocks above prove *when* we close; this proves closing is safe.

    ``transaction=True`` so the test body is not itself inside an atomic
    block — otherwise the release would (correctly) do nothing.
    """

    def test_orm_reconnects_with_search_path_after_release(self):
        from django.conf import settings
        from django.db import connection as real_connection

        from workflow_manager.workflow_v2.models.execution import WorkflowExecution

        WorkflowExecution.objects.count()
        assert real_connection.connection is not None

        WorkflowHelper._release_db_connection()
        assert real_connection.connection is None

        # The post-wait reads (row refetch, acknowledge) reconnect lazily...
        assert WorkflowExecution.objects.count() == 0
        assert real_connection.connection is not None
        # ...and custom_db re-applies the schema on that new connection.
        with real_connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            assert cursor.fetchone()[0] == settings.DB_SCHEMA

    def test_unexpired_persistent_connection_is_kept(self):
        from django.db import connection as real_connection

        from workflow_manager.workflow_v2.models.execution import WorkflowExecution

        WorkflowExecution.objects.count()
        # What CONN_MAX_AGE=None (persistent) sets at connect time. Restored, so
        # the shared connection is recyclable again for later tests.
        saved_close_at = real_connection.close_at
        real_connection.close_at = None
        try:
            raw = real_connection.connection
            WorkflowHelper._release_db_connection()
            assert real_connection.connection is raw
        finally:
            real_connection.close_at = saved_close_at

    def test_closed_connection_is_not_reopened(self):
        from django.db import connection as real_connection

        real_connection.close()

        WorkflowHelper._release_db_connection()

        assert real_connection.connection is None

    def test_release_inside_atomic_keeps_transaction_usable(self):
        from django.db import connection as real_connection
        from django.db import transaction

        from workflow_manager.workflow_v2.models.execution import WorkflowExecution

        with transaction.atomic():
            WorkflowExecution.objects.count()
            WorkflowHelper._release_db_connection()
            assert real_connection.connection is not None
            assert WorkflowExecution.objects.count() == 0
