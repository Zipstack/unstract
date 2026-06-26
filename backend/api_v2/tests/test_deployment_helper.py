"""Regression test for UN-3648.

When an API-deployment run fails synchronously at the "Staging files in API
storage" step (``SourceConnector.add_input_file_to_api_storage``, before async
dispatch), the PENDING ``WorkflowExecution`` row created earlier must be marked
ERROR — otherwise the UI shows the run as stuck/running forever.

Before the fix, staging sat *outside* the try/except in
``DeploymentHelper.execute_workflow``, so a staging exception propagated out of
the method and the row stayed PENDING. The fix gives staging its own
try/except that marks the execution ERROR (with the error-marking isolated so
cleanup still runs if that DB write fails) and then releases the rate-limit
slot and cleans up storage.

Like ``usage_v2/tests/test_helper.py``, this test does not require a live Django
database (the backend test env has no ``pytest-django`` / no DB). It stubs the
module's cross-app imports in ``sys.modules`` *before* importing the helper, so
the real ``execute_workflow`` control flow is exercised with the collaborators
mocked. Runnable under pytest or directly: ``python3 test_deployment_helper.py``.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# Ensure the backend dir (which holds the ``api_v2`` package) is importable when
# this file is run directly, not just under pytest's rootdir.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


class _AutoModule(types.ModuleType):
    """Module whose attribute access lazily returns (and caches) a MagicMock."""

    def __getattr__(self, name: str) -> MagicMock:
        mock = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, mock)
        return mock


def _install_stub(dotted: str) -> None:
    """Register an ``_AutoModule`` for ``dotted`` and every parent prefix.

    Existing entries (e.g. the real, empty ``api_v2`` package) are preserved so
    the real ``api_v2.deployment_helper`` submodule can still be imported.
    """
    parts = dotted.split(".")
    for i in range(1, len(parts) + 1):
        prefix = ".".join(parts[:i])
        if prefix not in sys.modules:
            sys.modules[prefix] = _AutoModule(prefix)


def _load_deployment_helper():
    """Stub cross-app imports, then import and return the real helper module."""
    import api_v2  # real, empty package — keep it so the submodule resolves

    assert not isinstance(api_v2, _AutoModule), "api_v2 must be the real package"

    for dotted in (
        "requests",
        "configuration.config_registry",
        "configuration.models",
        "django.conf",
        "django.core.files.uploadedfile",
        "plugins.workflow_manager.workflow_v2.api_hub_usage_utils",
        "rest_framework.request",
        "rest_framework.serializers",
        "rest_framework.utils.serializer_helpers",
        "tags.models",
        "usage_v2.helper",
        "utils.constants",
        "utils.local_context",
        "workflow_manager.endpoint_v2.destination",
        "workflow_manager.endpoint_v2.source",
        "workflow_manager.workflow_v2.dto",
        "workflow_manager.workflow_v2.enums",
        "workflow_manager.workflow_v2.execution",
        "workflow_manager.workflow_v2.models",
        "workflow_manager.workflow_v2.workflow_helper",
        "api_v2.api_key_validator",
        "api_v2.dto",
        "api_v2.exceptions",
        "api_v2.key_helper",
        "api_v2.models",
        "api_v2.rate_limiter",
        "api_v2.serializers",
        "api_v2.utils",
    ):
        _install_stub(dotted)

    # ``class DeploymentHelper(BaseAPIKeyValidator)`` needs a real base class,
    # not a MagicMock instance.
    sys.modules["api_v2.api_key_validator"].BaseAPIKeyValidator = type(
        "BaseAPIKeyValidator", (), {}
    )

    import api_v2.deployment_helper as helper

    return helper


def _make_helper_and_api(staging_error: Exception):
    """Load the helper with a known execution id and a failing staging call."""
    helper = _load_deployment_helper()

    # The module is cached in sys.modules, so its mocked collaborators are shared
    # across tests. Reset call counts and side effects so each test is isolated.
    for collaborator in (
        helper.WorkflowExecutionServiceHelper,
        helper.SourceConnector,
        helper.APIDeploymentRateLimiter,
        helper.DestinationConnector,
        helper.WorkflowHelper,
    ):
        collaborator.reset_mock(return_value=True, side_effect=True)

    # Known execution id so we can assert it is the one marked ERROR.
    execution_row = MagicMock()
    execution_row.id = "exec-123"
    helper.WorkflowExecutionServiceHelper.create_workflow_execution.return_value = (
        execution_row
    )

    # Simulate the synchronous staging failure (e.g. the Moody's S3/MinIO 403).
    helper.SourceConnector.add_input_file_to_api_storage.side_effect = staging_error

    api = MagicMock()
    api.workflow.id = "wf-1"
    api.id = "pipe-1"
    return helper, api


def _run_staging_failure() -> None:
    """A staging failure marks the execution ERROR instead of leaving it PENDING."""
    helper, api = _make_helper_and_api(RuntimeError("boom"))

    # Must NOT raise — the failure should be handled, not propagated.
    helper.DeploymentHelper.execute_workflow(
        organization_name="org",
        api=api,
        file_objs=[],
        timeout=-1,
    )

    # The PENDING row is marked ERROR with the surfaced reason.
    helper.WorkflowExecutionServiceHelper.update_execution_err.assert_called_once_with(
        "exec-123", "boom"
    )
    # And the slot/storage cleanup still runs.
    helper.APIDeploymentRateLimiter.release_slot.assert_called_once()
    helper.DestinationConnector.delete_api_storage_dir.assert_called_once()

    # Async dispatch is never reached when staging fails.
    helper.WorkflowHelper.execute_workflow_async.assert_not_called()


def _run_staging_failure_db_marking_raises() -> None:
    """If marking the row ERROR itself raises, cleanup must still run (not propagate)."""
    helper, api = _make_helper_and_api(RuntimeError("boom"))

    # The DB write to mark ERROR fails (e.g. transient DB error).
    helper.WorkflowExecutionServiceHelper.update_execution_err.side_effect = RuntimeError(
        "db down"
    )

    # Must NOT raise — a failed error-marking should not break cleanup.
    # The helper logs the failure via logger.exception; silence it so the
    # expected, handled error doesn't look like a test failure in the output.
    helper.logger.disabled = True
    try:
        helper.DeploymentHelper.execute_workflow(
            organization_name="org",
            api=api,
            file_objs=[],
            timeout=-1,
        )
    finally:
        helper.logger.disabled = False

    # Cleanup still runs even though error-marking raised.
    helper.APIDeploymentRateLimiter.release_slot.assert_called_once()
    helper.DestinationConnector.delete_api_storage_dir.assert_called_once()


def test_staging_failure_marks_execution_error() -> None:
    _run_staging_failure()


def test_staging_failure_cleanup_survives_db_marking_error() -> None:
    _run_staging_failure_db_marking_raises()


if __name__ == "__main__":
    _run_staging_failure()
    _run_staging_failure_db_marking_raises()
    print(
        "OK: staging failure marks execution ERROR + cleanup survives DB error (UN-3648)"
    )
