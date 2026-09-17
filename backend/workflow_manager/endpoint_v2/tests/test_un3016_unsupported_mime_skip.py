"""UN-3016: a file rejected for an unsupported MIME type must not reach a worker.

``SourceConnector.add_input_file_to_api_storage`` deliberately does not stage
the bytes of a file whose MIME type is not allowed. It used to return that file
anyway, with ``is_executed=True`` and a placeholder hash; nothing downstream
filters on ``is_executed``, so a worker picked the file up, failed on the file
that was never written, and the whole execution died with an opaque
"Execution: <path>; Destination: <path>" message. These tests pin the fix: the
rejected file is excluded from the returned mapping, the supported files in the
same request still go through, and an all-rejected request fails loudly with a
message that names what was rejected.

DB-free by construction: the ORM boundary (``Workflow.objects.get``) and the
file storage are patched, so nothing here needs Postgres. Files are real
``SimpleUploadedFile`` objects rather than mocks — a mock's ``content_type`` is
not in ``AllowedFileTypes``, so a mocked "supported" file would silently take
the skip branch and the test would pass for the wrong reason.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from workflow_manager.endpoint_v2.exceptions import (  # noqa: E402
    UnsupportedMimeTypeError,
)
from workflow_manager.endpoint_v2.source import SourceConnector  # noqa: E402

SUPPORTED_MIME = "application/pdf"
UNSUPPORTED_MIME = "application/x-msdownload"


def _upload(name: str, content_type: str) -> SimpleUploadedFile:
    """A real uploaded file: gives .name, .content_type, .size and .chunks()."""
    return SimpleUploadedFile(name, b"some bytes", content_type=content_type)


def _stage(file_objs: list[SimpleUploadedFile]) -> dict:
    """Call the staging helper with every external boundary patched out."""
    with (
        patch("workflow_manager.endpoint_v2.source.UserContext") as mock_user_context,
        patch("workflow_manager.endpoint_v2.source.WorkflowLog"),
        patch("workflow_manager.endpoint_v2.source.Workflow") as mock_workflow,
        patch("workflow_manager.endpoint_v2.source.FileSystem"),
        patch.object(
            SourceConnector,
            "get_api_storage_dir_path",
            return_value="unstract/api/org/exec-1",
        ),
    ):
        mock_user_context.get_organization_identifier.return_value = "org"
        mock_workflow.objects.get.return_value = MagicMock()
        return SourceConnector.add_input_file_to_api_storage(
            pipeline_id="pipeline-1",
            workflow_id="workflow-1",
            execution_id="exec-1",
            file_objs=file_objs,
        )


def test_partial_skip_returns_only_the_supported_files():
    """The core fix: a rejected file is absent from the returned mapping, and
    the supported file alongside it is unaffected.

    Also pins that a partial skip does NOT raise — rejecting some files while
    others are runnable proceeds with what can be run (UN-4055 tracks whether
    that should stay the behaviour).
    """
    file_hashes = _stage(
        [
            _upload("good.pdf", SUPPORTED_MIME),
            _upload("bad.exe", UNSUPPORTED_MIME),
        ]
    )

    assert "bad.exe" not in file_hashes
    assert "good.pdf" in file_hashes
    assert len(file_hashes) == 1
    assert file_hashes["good.pdf"].mime_type == SUPPORTED_MIME
    assert file_hashes["good.pdf"].file_name == "good.pdf"


def test_supported_file_is_staged_with_a_real_hash():
    """An accepted file's FileHash carries the sha256 of the bytes that were
    staged.

    Characterisation only: this held before the fix too, and no mutation of the
    fix makes it fail. It is here to document what a returned entry looks like,
    which is what makes the rejected file's absence elsewhere meaningful.
    """
    file_hashes = _stage([_upload("good.pdf", SUPPORTED_MIME)])

    assert set(file_hashes) == {"good.pdf"}
    file_hash = file_hashes["good.pdf"].file_hash
    assert len(file_hash) == 64
    assert all(c in "0123456789abcdef" for c in file_hash)


def test_total_skip_raises_naming_the_skipped_files():
    """When nothing survives the filter there is nothing to run: fail with the
    reason instead of dispatching an empty execution that reports success.
    """
    with pytest.raises(UnsupportedMimeTypeError) as excinfo:
        _stage(
            [
                _upload("bad.exe", UNSUPPORTED_MIME),
                _upload("worse.dll", UNSUPPORTED_MIME),
            ]
        )

    message = str(excinfo.value)
    assert "bad.exe" in message
    assert "worse.dll" in message
    assert UNSUPPORTED_MIME in message


def test_no_files_at_all_returns_empty_without_raising():
    """An empty request has no skipped files, so it is not an unsupported-type
    failure — the raise is guarded on there being something skipped.
    """
    assert _stage([]) == {}
