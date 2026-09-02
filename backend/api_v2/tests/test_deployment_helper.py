"""Regression tests for synchronous staging failures in ``execute_workflow``.

When an API-deployment run fails synchronously at the "Staging files in API
storage" step (``SourceConnector.add_input_file_to_api_storage``, before async
dispatch), the PENDING ``WorkflowExecution`` row created earlier must be marked
ERROR — otherwise the UI shows the run as stuck/running forever. The
error-marking is isolated so the rate-limit slot release and storage cleanup
still run even if that DB write fails.

Unit tests: the real ``execute_workflow`` control flow runs with every
DB/storage-touching collaborator patched on the imported module, so no
database is needed.
"""

from unittest import mock
from unittest.mock import MagicMock

import pytest

import api_v2.deployment_helper as dh


@pytest.fixture
def collaborators():
    """Patch execute_workflow's collaborators; staging fails with 'boom'."""
    with mock.patch.multiple(
        dh,
        WorkflowExecutionServiceHelper=mock.DEFAULT,
        SourceConnector=mock.DEFAULT,
        DestinationConnector=mock.DEFAULT,
        APIDeploymentRateLimiter=mock.DEFAULT,
        WorkflowHelper=mock.DEFAULT,
        Tag=mock.DEFAULT,
        logger=mock.DEFAULT,
    ) as mocks:
        execution_row = MagicMock()
        execution_row.id = "exec-123"
        mocks[
            "WorkflowExecutionServiceHelper"
        ].create_workflow_execution.return_value = execution_row
        mocks["SourceConnector"].add_input_file_to_api_storage.side_effect = RuntimeError(
            "boom"
        )
        yield mocks


def _api() -> MagicMock:
    api = MagicMock()
    api.workflow.id = "wf-1"
    api.id = "pipe-1"
    return api


def test_staging_failure_marks_execution_error(collaborators) -> None:
    """A staging failure marks the execution ERROR instead of leaving it PENDING."""
    # Must NOT raise — the failure should be handled, not propagated.
    dh.DeploymentHelper.execute_workflow(
        organization_name="org",
        api=_api(),
        file_objs=[],
        timeout=-1,
    )

    # The PENDING row is marked ERROR with the surfaced reason.
    collaborators[
        "WorkflowExecutionServiceHelper"
    ].update_execution_err.assert_called_once_with("exec-123", "boom")
    # And the slot/storage cleanup still runs.
    collaborators["APIDeploymentRateLimiter"].release_slot.assert_called_once()
    collaborators["DestinationConnector"].delete_api_storage_dir.assert_called_once()
    # Async dispatch is never reached when staging fails.
    collaborators["WorkflowHelper"].execute_workflow_async.assert_not_called()


def test_staging_failure_cleanup_survives_db_marking_error(collaborators) -> None:
    """If marking the row ERROR itself raises, cleanup must still run (not propagate)."""
    collaborators[
        "WorkflowExecutionServiceHelper"
    ].update_execution_err.side_effect = RuntimeError("db down")

    # Must NOT raise — a failed error-marking should not break cleanup.
    dh.DeploymentHelper.execute_workflow(
        organization_name="org",
        api=_api(),
        file_objs=[],
        timeout=-1,
    )

    # Cleanup still runs even though error-marking raised.
    collaborators["APIDeploymentRateLimiter"].release_slot.assert_called_once()
    collaborators["DestinationConnector"].delete_api_storage_dir.assert_called_once()


@pytest.fixture
def staging_rejects_everything():
    """Patch execute_workflow's collaborators; staging returns no dispatchable files."""
    with mock.patch.multiple(
        dh,
        WorkflowExecutionServiceHelper=mock.DEFAULT,
        SourceConnector=mock.DEFAULT,
        DestinationConnector=mock.DEFAULT,
        APIDeploymentRateLimiter=mock.DEFAULT,
        WorkflowHelper=mock.DEFAULT,
        ResultCacheUtils=mock.DEFAULT,
        Tag=mock.DEFAULT,
        logger=mock.DEFAULT,
    ) as mocks:
        execution_row = MagicMock()
        execution_row.id = "exec-123"
        mocks[
            "WorkflowExecutionServiceHelper"
        ].create_workflow_execution.return_value = execution_row
        mocks["SourceConnector"].add_input_file_to_api_storage.return_value = {}
        mocks["ResultCacheUtils"].get_api_results.return_value = [
            {"file": "evil.pdf", "status": "Failed", "error": "unsupported MIME type"}
        ]
        completed_row = MagicMock()
        completed_row.status = "COMPLETED"
        mocks[
            "WorkflowExecutionServiceHelper"
        ].update_execution_completed.return_value = completed_row
        yield mocks


def test_all_files_rejected_completes_without_dispatch(
    staging_rejects_everything,
) -> None:
    """A request whose every file is rejected must reach a terminal status.

    The worker short-circuits an empty file set without writing a status back, so
    dispatching one strands the execution in PENDING and the caller polls forever.
    """
    mocks = staging_rejects_everything
    # A non-empty upload whose staging result is empty. Passing [] instead would
    # leave the branch satisfied by `not file_objs` too, and the original bug -
    # dispatching a request whose files were all rejected - would pass this test.
    response = dh.DeploymentHelper.execute_workflow(
        organization_name="org",
        api=_api(),
        file_objs=[MagicMock()],
        timeout=-1,
    )

    # Nothing is dispatched...
    mocks["WorkflowHelper"].execute_workflow_async.assert_not_called()
    # ...the row is terminalised here instead of being left PENDING, and the
    # counters are written so the run does not read back as a clean success...
    mocks[
        "WorkflowExecutionServiceHelper"
    ].update_execution_completed.assert_called_once_with(
        "exec-123", total_files=1, failed_files=1
    )
    # ...the slot and staging dir are released...
    mocks["APIDeploymentRateLimiter"].release_slot.assert_called_once()
    mocks["DestinationConnector"].delete_api_storage_dir.assert_called_once()
    # ...and the caller still sees why each file failed.
    assert response["execution_status"] == "COMPLETED"
    assert response["result"][0]["file"] == "evil.pdf"
    assert response["result"][0]["status"] == "Failed"


def test_files_staged_successfully_are_dispatched(staging_rejects_everything) -> None:
    """The short-circuit must not fire when staging did return files.

    Sibling to the test above: together they pin the branch to the staging result
    rather than to the upload list.
    """
    mocks = staging_rejects_everything
    mocks["SourceConnector"].add_input_file_to_api_storage.return_value = {
        "good.pdf": MagicMock()
    }

    dh.DeploymentHelper.execute_workflow(
        organization_name="org",
        api=_api(),
        file_objs=[MagicMock()],
        timeout=-1,
    )

    mocks["WorkflowHelper"].execute_workflow_async.assert_called_once()
    mocks["WorkflowExecutionServiceHelper"].update_execution_completed.assert_not_called()


def test_all_files_rejected_cleanup_survives_db_marking_error(
    staging_rejects_everything,
) -> None:
    """A failing status write must not strand the slot or the staging dir.

    update_execution_completed only catches DoesNotExist, so a lock timeout or a
    dropped connection propagates; without isolation the org's rate limit slot
    stays held for its full TTL and throttles every other call for that org.
    """
    mocks = staging_rejects_everything
    mocks[
        "WorkflowExecutionServiceHelper"
    ].update_execution_completed.side_effect = Exception("db is down")

    response = dh.DeploymentHelper.execute_workflow(
        organization_name="org",
        api=_api(),
        file_objs=[MagicMock()],
        timeout=-1,
    )

    mocks["APIDeploymentRateLimiter"].release_slot.assert_called_once()
    mocks["DestinationConnector"].delete_api_storage_dir.assert_called_once()
    # The row never reached COMPLETED, so the response must not claim it did.
    assert response["execution_status"] == "ERROR"
