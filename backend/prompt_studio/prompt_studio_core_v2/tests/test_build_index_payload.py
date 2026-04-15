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

The backend test environment has no ``pytest-django``, no SQLite
fallback, and the helper has a heavy Django-coupled import surface.
Rather than spin up Django, we stub every collaborator as a
``MagicMock`` on ``sys.modules`` *before* importing the helper, and
then patch ``PromptStudioHelper`` class methods per-test.  This mirrors
the ``usage_v2/tests/test_helper.py`` approach.

If the helper module cannot be imported in a given environment (for
example because the stub surface has drifted), all tests in the module
are skipped with a clear reason.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub every collaborator module on sys.modules before importing the helper.
# These stubs are intentionally broad MagicMocks — the tests patch the
# specific attributes they care about via ``unittest.mock.patch``.
# ---------------------------------------------------------------------------


def _install(name: str, attrs: dict[str, Any] | None = None) -> types.ModuleType:
    """Install (or replace) a fake module into ``sys.modules``.

    Always creates a fresh ``ModuleType``; this is important because the
    real module may already have been imported before these stubs run
    (via pytest collection, conftest, etc.), and we need our fake to
    actually take effect.
    """
    mod = types.ModuleType(name)
    if attrs:
        for key, value in attrs.items():
            setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _install_package(name: str) -> types.ModuleType:
    """Install a fake package (marked with ``__path__``).

    Only stubs the package if it is not already in ``sys.modules``.
    This prevents clobbering packages like ``unstract.core`` that must
    retain their real ``__path__`` for submodule resolution.  The child
    modules we care about are always replaced explicitly via
    ``_install``.
    """
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


try:
    # Account / adapter stubs
    _install_package("account_v2")
    _install(
        "account_v2.constants",
        {"Common": type("Common", (), {"LOG_EVENTS_ID": "log_events_id",
                                        "REQUEST_ID": "request_id"})},
    )
    _install("account_v2.models", {"User": MagicMock(name="User")})
    _install_package("adapter_processor_v2")
    _install(
        "adapter_processor_v2.constants",
        {"AdapterKeys": type("AdapterKeys", (), {})},
    )
    _install(
        "adapter_processor_v2.models",
        {"AdapterInstance": MagicMock(name="AdapterInstance")},
    )

    # Plugins stub
    _install("plugins", {"get_plugin": MagicMock(return_value=None)})

    # utils stubs
    _install_package("utils")
    _install_package("utils.file_storage")
    _install(
        "utils.file_storage.constants",
        {
            "FileStorageKeys": type(
                "FileStorageKeys",
                (),
                {"PERMANENT_REMOTE_STORAGE": "permanent"},
            )
        },
    )
    _install_package("utils.file_storage.helpers")
    _install(
        "utils.file_storage.helpers.prompt_studio_file_helper",
        {"PromptStudioFileHelper": MagicMock(name="PromptStudioFileHelper")},
    )
    _install(
        "utils.local_context",
        {"StateStore": MagicMock(name="StateStore")},
    )

    # backend.celery_service stub
    _install_package("backend")
    _install(
        "backend.celery_service",
        {"app": MagicMock(name="celery_app")},
    )

    # prompt_studio stubs
    _install_package("prompt_studio")
    _install_package("prompt_studio.prompt_profile_manager_v2")
    _install(
        "prompt_studio.prompt_profile_manager_v2.models",
        {"ProfileManager": MagicMock(name="ProfileManager")},
    )
    _install(
        "prompt_studio.prompt_profile_manager_v2.profile_manager_helper",
        {"ProfileManagerHelper": MagicMock(name="ProfileManagerHelper")},
    )

    _install_package("prompt_studio.prompt_studio_document_manager_v2")
    _install(
        "prompt_studio.prompt_studio_document_manager_v2.models",
        {"DocumentManager": MagicMock(name="DocumentManager")},
    )

    _install_package("prompt_studio.prompt_studio_index_manager_v2")
    _install(
        "prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper",
        {"PromptStudioIndexHelper": MagicMock(name="PromptStudioIndexHelper")},
    )

    _install_package("prompt_studio.prompt_studio_output_manager_v2")
    _install(
        "prompt_studio.prompt_studio_output_manager_v2.output_manager_helper",
        {"OutputManagerHelper": MagicMock(name="OutputManagerHelper")},
    )

    _install_package("prompt_studio.prompt_studio_v2")
    _install(
        "prompt_studio.prompt_studio_v2.models",
        {"ToolStudioPrompt": MagicMock(name="ToolStudioPrompt")},
    )

    # Stub the prompt_studio_core_v2 sibling modules too — several of them
    # transitively import modules (like ``utils.cache_service``) that we
    # don't want to pull in for these unit tests.
    _install_package("prompt_studio.prompt_studio_core_v2")
    _install(
        "prompt_studio.prompt_studio_core_v2.document_indexing_service",
        {"DocumentIndexingService": MagicMock(name="DocumentIndexingService")},
    )

    # Real exception classes — build_index_payload uses ``raise``.
    class _FakeExc(Exception):
        pass

    _install(
        "prompt_studio.prompt_studio_core_v2.exceptions",
        {
            "AnswerFetchError": type("AnswerFetchError", (_FakeExc,), {}),
            "DefaultProfileError": type("DefaultProfileError", (_FakeExc,), {}),
            "EmptyPromptError": type("EmptyPromptError", (_FakeExc,), {}),
            "ExtractionAPIError": type("ExtractionAPIError", (_FakeExc,), {}),
            "IndexingAPIError": type("IndexingAPIError", (_FakeExc,), {}),
            "NoPromptsFound": type("NoPromptsFound", (_FakeExc,), {}),
            "OperationNotSupported": type("OperationNotSupported", (_FakeExc,), {}),
            "PermissionError": type("PermissionError", (_FakeExc,), {}),
        },
    )
    _install(
        "prompt_studio.prompt_studio_core_v2.migration_utils",
        {"SummarizeMigrationUtils": MagicMock(name="SummarizeMigrationUtils")},
    )
    _install(
        "prompt_studio.prompt_studio_core_v2.models",
        {"CustomTool": MagicMock(name="CustomTool")},
    )
    _install(
        "prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool",
        {"PromptIdeBaseTool": MagicMock(name="PromptIdeBaseTool")},
    )
    _install(
        "prompt_studio.prompt_studio_core_v2.prompt_variable_service",
        {"PromptStudioVariableService": MagicMock(name="PromptStudioVariableService")},
    )

    # unstract.core.pubsub_helper stub (LogPublisher isn't used by
    # build_index_payload but the module-level import must succeed).
    _install_package("unstract.core")
    _install(
        "unstract.core.pubsub_helper",
        {"LogPublisher": MagicMock(name="LogPublisher")},
    )

    # unstract.sdk1 stubs — these heavy modules transitively pull in
    # ``unstract.core.cache.redis_client`` which isn't on the python
    # path for the backend tests.  We only need the leaf classes.
    _install_package("unstract.sdk1")
    _install(
        "unstract.sdk1.constants",
        {
            "LogLevel": type(
                "LogLevel", (), {"INFO": "INFO", "WARN": "WARN", "ERROR": "ERROR"}
            )
        },
    )
    _install(
        "unstract.sdk1.exceptions",
        {
            "IndexingError": type("IndexingError", (Exception,), {}),
            "SdkError": type("SdkError", (Exception,), {}),
        },
    )
    _install_package("unstract.sdk1.execution")

    class _FakeExecutionContext:
        """Minimal ExecutionContext that keeps ``executor_params`` as
        the real dict we pass in (the tests inspect it)."""

        def __init__(self, **kwargs: Any) -> None:
            self.executor_name = kwargs.get("executor_name")
            self.operation = kwargs.get("operation")
            self.run_id = kwargs.get("run_id")
            self.execution_source = kwargs.get("execution_source")
            self.organization_id = kwargs.get("organization_id")
            self.executor_params = kwargs.get("executor_params") or {}
            self.request_id = kwargs.get("request_id")
            self.log_events_id = kwargs.get("log_events_id")

    _install(
        "unstract.sdk1.execution.context",
        {"ExecutionContext": _FakeExecutionContext},
    )
    _install(
        "unstract.sdk1.execution.dispatcher",
        {"ExecutionDispatcher": MagicMock(name="ExecutionDispatcher")},
    )
    _install_package("unstract.sdk1.file_storage")
    _install(
        "unstract.sdk1.file_storage.constants",
        {"StorageType": type("StorageType", (), {"PERMANENT": "permanent"})},
    )
    _install(
        "unstract.sdk1.file_storage.env_helper",
        {"EnvHelper": MagicMock(name="EnvHelper")},
    )
    _install_package("unstract.sdk1.utils")
    _install(
        "unstract.sdk1.utils.indexing",
        {"IndexingUtils": MagicMock(name="IndexingUtils")},
    )
    _install(
        "unstract.sdk1.utils.tool",
        {"ToolUtils": MagicMock(name="ToolUtils")},
    )

    # Now import the helper module.  If this fails, all tests below will
    # be skipped via the ``_IMPORT_ERROR`` sentinel.
    from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod  # noqa: E402

    PromptStudioHelper = _psh_mod.PromptStudioHelper
    IKeys = _psh_mod.IKeys
    _IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover — environment guard
    _IMPORT_ERROR = (
        f"prompt_studio_helper could not be imported in this environment: "
        f"{type(exc).__name__}: {exc}"
    )
    PromptStudioHelper = None  # type: ignore[assignment]
    IKeys = None  # type: ignore[assignment]


pytestmark = pytest.mark.skipif(
    _IMPORT_ERROR is not None, reason=_IMPORT_ERROR or ""
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

    # Patch everything via context managers so each test starts clean.
    patches = [
        patch.object(
            _psh_mod.CustomTool,
            "objects",
            MagicMock(get=MagicMock(return_value=tool)),
        ),
        patch.object(
            _psh_mod.PromptStudioFileHelper,
            "get_or_create_prompt_studio_subdirectory",
            return_value="/prompt-studio/org/user/tool",
        ),
        patch.object(
            _psh_mod.ProfileManager,
            "get_default_llm_profile",
            return_value=profile,
        ),
        patch.object(
            PromptStudioHelper,
            "validate_adapter_status",
            return_value=None,
        ),
        patch.object(
            PromptStudioHelper,
            "validate_profile_manager_owner_access",
            return_value=None,
        ),
        patch.object(
            PromptStudioHelper,
            "_get_platform_api_key",
            return_value="pk-test",
        ),
        patch.object(
            PromptStudioHelper,
            "_build_summarize_params",
            return_value=(None, "", MagicMock()),
        ),
        patch.object(
            _psh_mod.EnvHelper,
            "get_storage",
            return_value=fs_instance,
        ),
        patch.object(
            _psh_mod.PromptStudioIndexHelper,
            "check_extraction_status",
            check_mock,
        ),
        patch.object(
            _psh_mod.IndexingUtils,
            "generate_index_key",
            return_value="doc-key-1",
        ),
        patch.object(
            _psh_mod,
            "PromptIdeBaseTool",
            MagicMock(return_value=MagicMock()),
        ),
        patch.object(
            _psh_mod.StateStore,
            "get",
            return_value="",
        ),
    ]
    for p in patches:
        p.start()
    try:
        context, cb_kwargs = PromptStudioHelper.build_index_payload(
            tool_id="tool-1",
            file_name="doc.pdf",
            org_id="org-1",
            user_id="user-1",
            document_id="doc-1",
            run_id="run-1",
        )
        return context, cb_kwargs, fs_instance, check_mock
    finally:
        for p in patches:
            p.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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
