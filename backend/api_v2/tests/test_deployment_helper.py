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
        mocks["SourceConnector"].add_input_file_to_api_storage.side_effect = (
            RuntimeError("boom")
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
    collaborators["WorkflowExecutionServiceHelper"].update_execution_err.side_effect = (
        RuntimeError("db down")
    )

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
