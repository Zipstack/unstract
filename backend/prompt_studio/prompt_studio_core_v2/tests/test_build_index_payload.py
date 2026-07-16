"""Regression tests for ``PromptStudioHelper.build_index_payload``.

These tests pin the Manage Documents → Index marker-reuse behaviour
introduced to fix the "extract runs every time" QA bug.  The helper
must:

  1. On a valid extraction marker + readable extract file, pre-populate
     ``index_params[IKeys.EXTRACTED_TEXT]`` so the executor's
     ``_handle_ide_index`` skips the extract step entirely.
  2. On a marker hit where the extract file is missing, fall back to
     full extraction (do NOT pre-populate the field).
  3. On a marker miss, fall back to full extraction.
  4. On an error inside ``check_extraction_status``, swallow the error
     and fall back to full extraction — the dispatch must not fail.

Unit tests: the real helper module is imported (Django is loaded by the
rig's test env) and every collaborator is patched on it per-test, so no
database is touched.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod

PromptStudioHelper = _psh_mod.PromptStudioHelper
IKeys = _psh_mod.IKeys


def _make_tool(enable_highlight: bool = False, summarize_context: bool = False):
    tool = MagicMock(name="CustomTool")
    tool.enable_highlight = enable_highlight
    tool.summarize_context = summarize_context
    return tool


def _make_profile():
    profile = MagicMock(name="ProfileManager")
    profile.x2text.id = "x2t-1"
    profile.x2text.metadata = {"model": "default"}
    profile.embedding_model.id = "emb-1"
    profile.vector_store.id = "vdb-1"
    profile.chunk_size = 512
    profile.chunk_overlap = 64
    profile.profile_id = "profile-1"
    return profile


def _dispatch_build(
    *,
    check_return: bool | Exception,
    read_return: str | Exception,
    tool: Any = None,
    profile: Any = None,
    validate_owner_mock: Any = None,
):
    """Run ``build_index_payload`` with all collaborators patched.

    ``check_return`` / ``read_return`` configure the two branches we
    care about:
        * ``check_return`` — ``check_extraction_status`` return value
          or an exception to raise.
        * ``read_return`` — ``fs_instance.read`` return value or an
          exception to raise.

    Returns the ``ExecutionContext`` built by ``build_index_payload``.
    """
    tool = tool or _make_tool()
    profile = profile or _make_profile()
    validate_owner_mock = validate_owner_mock or MagicMock(return_value=None)

    fs_instance = MagicMock(name="fs_instance")
    if isinstance(read_return, Exception):
        fs_instance.read.side_effect = read_return
    else:
        fs_instance.read.return_value = read_return

    check_mock = MagicMock(name="check_extraction_status")
    if isinstance(check_return, Exception):
        check_mock.side_effect = check_return
    else:
        check_mock.return_value = check_return

    with ExitStack() as stack:
        for target, attr, value in (
            (_psh_mod.CustomTool, "objects", MagicMock(get=MagicMock(return_value=tool))),
            (
                _psh_mod.PromptStudioFileHelper,
                "get_or_create_prompt_studio_subdirectory",
                MagicMock(return_value="/prompt-studio/org/user/tool"),
            ),
            (
                _psh_mod.ProfileManager,
                "get_default_llm_profile",
                MagicMock(return_value=profile),
            ),
            (PromptStudioHelper, "validate_adapter_status", MagicMock(return_value=None)),
            (
                PromptStudioHelper,
                "validate_profile_manager_owner_access",
                validate_owner_mock,
            ),
            (
                PromptStudioHelper,
                "_get_platform_api_key",
                MagicMock(return_value="pk-test"),
            ),
            (
                PromptStudioHelper,
                "_build_summarize_params",
                MagicMock(return_value=(None, "", MagicMock())),
            ),
            (_psh_mod.EnvHelper, "get_storage", MagicMock(return_value=fs_instance)),
            (_psh_mod.PromptStudioIndexHelper, "check_extraction_status", check_mock),
            (
                _psh_mod.IndexingUtils,
                "generate_index_key",
                MagicMock(return_value="doc-key-1"),
            ),
            (_psh_mod, "PromptIdeBaseTool", MagicMock(return_value=MagicMock())),
            (_psh_mod.StateStore, "get", MagicMock(return_value="")),
        ):
            stack.enter_context(patch.object(target, attr, value))

        context, cb_kwargs = PromptStudioHelper.build_index_payload(
            tool_id="tool-1",
            file_name="doc.pdf",
            org_id="org-1",
            user_id="user-1",
            document_id="doc-1",
            run_id="run-1",
            request_user_id="requester-1",
        )
        return context, cb_kwargs, fs_instance, check_mock


class TestBuildIndexPayloadMarker:
    """Verify that build_index_payload honours the extraction marker."""

    def test_marker_hit_prepopulates_extracted_text(self) -> None:
        """Marker True + file readable → EXTRACTED_TEXT is pre-populated."""
        context, _cb, fs_instance, check_mock = _dispatch_build(
            check_return=True,
            read_return="existing extracted content",
        )
        index_params = context.executor_params["index_params"]
        assert index_params[IKeys.EXTRACTED_TEXT] == "existing extracted content"
        fs_instance.read.assert_called_once()
        check_mock.assert_called_once()

    def test_marker_hit_missing_file_does_not_prepopulate(self) -> None:
        """Marker True + FileNotFoundError → field NOT set, fall back to extract."""
        context, _cb, fs_instance, _check = _dispatch_build(
            check_return=True,
            read_return=FileNotFoundError("missing"),
        )
        index_params = context.executor_params["index_params"]
        assert IKeys.EXTRACTED_TEXT not in index_params
        fs_instance.read.assert_called_once()

    def test_marker_miss_does_not_prepopulate(self) -> None:
        """Marker False → EXTRACTED_TEXT NOT set, extract runs as before."""
        context, _cb, fs_instance, _check = _dispatch_build(
            check_return=False,
            read_return="should-not-be-read",
        )
        index_params = context.executor_params["index_params"]
        assert IKeys.EXTRACTED_TEXT not in index_params
        fs_instance.read.assert_not_called()

    def test_check_extraction_status_raises_is_swallowed(self, caplog) -> None:
        """check_extraction_status error → warn, field NOT set, no re-raise."""
        import logging as _logging

        caplog.set_level(_logging.WARNING, logger=_psh_mod.logger.name)
        context, _cb, fs_instance, _check = _dispatch_build(
            check_return=RuntimeError("db down"),
            read_return="should-not-be-read",
        )
        index_params = context.executor_params["index_params"]
        assert IKeys.EXTRACTED_TEXT not in index_params
        fs_instance.read.assert_not_called()
        # A warning should have been emitted about the fallback.
        assert any(
            "falling back to full extraction" in rec.getMessage()
            for rec in caplog.records
        )


class TestOwnerAccessPlumbing:
    """UN-3739: the REQUESTER must reach the owner-access check.

    ``user_id`` in these helpers is the file-path owner (the project
    creator) — views pass ``tool.created_by.user_id`` there.  The
    requesting user travels separately as ``request_user_id``; asserting
    it differs from ``user_id`` pins that the two identities are never
    conflated again.
    """

    def test_owner_access_receives_requesting_user(self) -> None:
        validate_owner_mock = MagicMock(return_value=None)
        _dispatch_build(
            check_return=True,
            read_return="extracted text",
            validate_owner_mock=validate_owner_mock,
        )
        _args, kwargs = validate_owner_mock.call_args
        assert kwargs.get("request_user_id") == "requester-1"
        assert kwargs.get("request_user_id") != "user-1"
