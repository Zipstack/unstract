"""UN-3016: a staging failure must clean up the API storage directory.

``WorkflowViewSet.execute`` stages uploaded files before running the workflow.
Staging can now fail part-way — ``add_input_file_to_api_storage`` raises
``UnsupportedMimeTypeError`` when every uploaded file is rejected, and it may
have written some files before reaching that point. The staging call therefore
sits inside the ``try`` whose handler calls ``delete_api_storage_dir``, and that
handler's guard (``has_uploads``) is exactly the condition under which staging
ran at all. These tests pin both halves: cleanup happens when staging fails,
and cleanup is not attempted for a request that never staged anything.

DB-free: the serializer, the workflow lookup and both connectors are patched,
so ``execute`` is exercised as pure control flow.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from workflow_manager.endpoint_v2.exceptions import (  # noqa: E402
    UnsupportedMimeTypeError,
)
from workflow_manager.workflow_v2.views import WorkflowViewSet  # noqa: E402

WORKFLOW_ID = "workflow-1"
EXECUTION_ID = "exec-1"

VIEWS = "workflow_manager.workflow_v2.views"


def _request(with_files: bool) -> MagicMock:
    request = MagicMock()
    request.FILES.getlist.return_value = [MagicMock()] if with_files else []
    return request


def _patched_serializer(stack):
    """Patch the serializer so execute() gets ids without parsing a payload."""
    serializer_cls = stack.enter_context(patch(f"{VIEWS}.ExecuteWorkflowSerializer"))
    serializer = serializer_cls.return_value
    serializer.get_workflow_id.return_value = WORKFLOW_ID
    serializer.get_execution_id.return_value = EXECUTION_ID
    serializer.get_execution_action.return_value = None
    return serializer


def test_staging_failure_deletes_the_api_storage_dir():
    """A staging failure leaves already-written files behind unless the handler
    cleans up, so the failure must reach ``delete_api_storage_dir``.
    """
    with ExitStack() as stack:
        _patched_serializer(stack)
        source = stack.enter_context(patch(f"{VIEWS}.SourceConnector"))
        destination = stack.enter_context(patch(f"{VIEWS}.DestinationConnector"))
        source.add_input_file_to_api_storage.side_effect = UnsupportedMimeTypeError(
            "No files could be processed. Unsupported file type(s): 'bad.exe'"
        )

        with pytest.raises(UnsupportedMimeTypeError):
            WorkflowViewSet().execute(_request(with_files=True))

        destination.delete_api_storage_dir.assert_called_once_with(
            workflow_id=WORKFLOW_ID, execution_id=EXECUTION_ID
        )


def test_no_cleanup_when_the_request_staged_nothing():
    """A request with no uploads never created a storage dir; a later failure
    must not try to delete one.
    """
    with ExitStack() as stack:
        _patched_serializer(stack)
        stack.enter_context(patch(f"{VIEWS}.SourceConnector"))
        destination = stack.enter_context(patch(f"{VIEWS}.DestinationConnector"))
        stack.enter_context(
            patch.object(
                WorkflowViewSet,
                "get_workflow_by_id",
                side_effect=RuntimeError("boom"),
            )
        )

        with pytest.raises(RuntimeError):
            WorkflowViewSet().execute(_request(with_files=False))

        destination.delete_api_storage_dir.assert_not_called()
