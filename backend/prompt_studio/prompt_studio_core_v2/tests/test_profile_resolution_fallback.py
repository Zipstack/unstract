"""Regression tests for profile resolution in ``fetch_response``.

Pins the fix for the CLI-surfaced bug where a prompt with no
``profile_manager`` FK raised ``DefaultProfileError`` even though the project
had a default LLM profile configured. ``index_document`` and single-pass
extraction already fell back to ``ProfileManager.get_default_llm_profile``;
``fetch_response`` was the lone omission.

The resolution ladder these tests lock down, in order:

  1. An explicitly passed ``profile_manager_id`` wins over everything.
  2. Otherwise the prompt's own ``profile_manager`` FK.
  3. Otherwise the project default -- the rung this PR added.
  4. If none resolves, ``DefaultProfileError`` propagates.

They also pin the second half of the fix: ``cb_kwargs["profile_manager_id"]``
must carry the profile *actually used*, not the (possibly ``None``) argument.
``OutputManagerHelper.get_default_profile`` treats ``None`` as "re-resolve the
project default", so passing the raw argument books output against a different
profile than the one that produced it.

These call the real ``build_fetch_response_payload`` /
``build_bulk_fetch_response_payload`` and patch only their collaborators, so
the assertions cover the shipped path end to end -- including everything after
the ladder.

An earlier version of this file extracted the ladder's source text and
``exec``'d it. It was replaced because it could not fail on the regressions it
existed to catch: it stayed green when the resolved profile was clobbered
immediately after the ladder, and when the ``cb_kwargs`` fix was reverted at
both call sites. Please do not reintroduce source-text assertions here.
"""

from __future__ import annotations

import os
import uuid
from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _deps():
    """Import the Django-coupled helper at call time, not import time.

    Skips only when Django itself is unavailable; configuration and application
    import failures propagate so a real regression is never hidden as a skip.
    """
    try:
        import django
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"django is not installed: {exc}")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
    django.setup()

    from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as psh
    from prompt_studio.prompt_studio_core_v2.exceptions import DefaultProfileError

    return psh, DefaultProfileError


EXPLICIT_ID = "11111111-1111-1111-1111-111111111111"
PROMPT_FK_ID = "22222222-2222-2222-2222-222222222222"
PROJECT_DEFAULT_ID = "33333333-3333-3333-3333-333333333333"

# build_bulk_fetch_response_payload takes a prompt list and never consults a
# single prompt's FK, so only the FK-precedence rung is scoped to the builder
# that reads one. Both builders carry the cb_kwargs fix.
FK_AWARE_BUILDERS = ["build_fetch_response_payload"]
ALL_BUILDERS = ["build_fetch_response_payload", "build_bulk_fetch_response_payload"]


def _make_profile(profile_id: str) -> Any:
    """A ProfileManager stand-in with the attributes the builders read.

    ``profile_id`` is a real ``UUID``, matching the ``UUIDField`` on the model.
    That is load-bearing: ``cb_kwargs`` is JSON-serialised by Celery
    (``task_serializer = "json"``), so dropping the ``str()`` wrapper in the
    helper would raise at dispatch. A ``str`` fake here would hide that.
    """
    profile = MagicMock(name=f"ProfileManager<{profile_id}>")
    profile.profile_id = uuid.UUID(profile_id)
    profile.chunk_size = 512
    profile.chunk_overlap = 64
    return profile


def _make_prompt(profile: Any) -> Any:
    prompt = MagicMock(name="ToolStudioPrompt")
    prompt.profile_manager = profile
    prompt.prompt_id = "prompt-1"
    return prompt


def _call(
    psh: Any,
    builder: str,
    *,
    profile_manager_id: str | None,
    prompt_profile: Any,
    default_profile: Any,
    default_raises: BaseException | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Invoke a real payload builder with every collaborator patched out.

    Only profile resolution stays real; everything downstream is stubbed so the
    call reaches ``cb_kwargs`` without touching storage, indexing or an LLM.

    ``get_profile_manager`` returns the explicit profile only when handed the
    ID under test, so the rung-1 assertion cannot pass vacuously.
    """
    helper = psh.PromptStudioHelper
    prompt = _make_prompt(prompt_profile)

    def _get_default(tool: Any) -> Any:
        if default_raises is not None:
            raise default_raises
        return default_profile

    def _get_explicit(profile_manager_id: str) -> Any:
        assert profile_manager_id == EXPLICIT_ID, (
            f"builder forwarded {profile_manager_id!r} to get_profile_manager, "
            f"expected {EXPLICIT_ID!r}"
        )
        return _make_profile(EXPLICIT_ID)

    # autospec on the collaborators whose signatures the builders call into, so
    # an arity or keyword change in production fails here instead of staying
    # green. The module-attribute patches below are legitimately opaque.
    patches = [
        patch.object(
            psh.ProfileManager,
            "get_default_llm_profile",
            autospec=True,
            side_effect=lambda tool: _get_default(tool),
        ),
        patch.object(
            psh.ProfileManagerHelper,
            "get_profile_manager",
            autospec=True,
            side_effect=lambda profile_manager_id: _get_explicit(profile_manager_id),
        ),
        patch.object(helper, "_resolve_llm_ids", autospec=True, return_value=("m", "c")),
        patch.object(helper, "validate_adapter_status", autospec=True),
        patch.object(helper, "validate_profile_manager_owner_access", autospec=True),
        patch.object(helper, "_get_platform_api_key", autospec=True, return_value="pk"),
        # dynamic_extractor returns an ExtractResult (text + optional
        # document_insights signature data), not a bare string.
        patch.object(
            helper,
            "dynamic_extractor",
            autospec=True,
            return_value=psh.ExtractResult(text="text"),
        ),
        # Must be a dict with a non-pending status: the builders early-return a
        # pending response (and no cb_kwargs) when indexing is still running.
        patch.object(
            helper, "dynamic_indexer", autospec=True, return_value={"status": "COMPLETED"}
        ),
        patch.object(helper, "_build_grammar_list", autospec=True, return_value=[]),
        patch.object(helper, "_build_prompt_output", autospec=True, return_value={}),
        # Returns the (mutated) output dict, so it must pass it through.
        patch.object(
            helper,
            "fetch_table_settings_if_enabled",
            autospec=True,
            side_effect=lambda _doc, _prompt, _org, _user, _tool, output: output,
        ),
        # Lookups no-op in OSS but hit the database in trees where the plugin is
        # installed, which the mock prompt can't satisfy. Stubbed so both take
        # the same path; the call itself is asserted below.
        patch.object(psh, "get_lookup_config", autospec=True, return_value=None),
        patch.object(psh, "EnvHelper", MagicMock()),
        patch.object(psh, "PromptIdeBaseTool", MagicMock()),
        patch.object(psh, "IndexingUtils", MagicMock()),
        patch.object(psh, "StateStore", MagicMock()),
        patch.object(psh, "ExecutionContext", MagicMock()),
        patch.object(psh, "PromptStudioVariableService", MagicMock()),
    ]
    # ExitStack, not a bare start loop: a mistargeted patch would otherwise
    # raise partway through and leak the already-started ones into later tests.
    with ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        kwargs: dict[str, Any] = {
            "tool": MagicMock(
                tool_id="tool-1",
                summarize_as_source=False,
                enable_highlight=False,
                enable_challenge=False,
            ),
            "doc_path": "/docs/a.pdf",
            "doc_name": "a.pdf",
            "org_id": "org-1",
            "user_id": "user-1",
            "document_id": "doc-1",
            "run_id": "run-1",
            "profile_manager_id": profile_manager_id,
            "request_user": None,
        }
        if builder == "build_bulk_fetch_response_payload":
            kwargs["prompts"] = [prompt]
        else:
            kwargs["prompt"] = prompt
        result = getattr(helper, builder)(**kwargs)
        # Stubbing the seam would otherwise let its call site be deleted
        # silently. Only the single-prompt builder consults it.
        if builder == "build_fetch_response_payload":
            psh.get_lookup_config.assert_called_once_with(prompt)
        return result


@pytest.mark.parametrize("builder", FK_AWARE_BUILDERS)
class TestProfileResolutionLadder:
    def test_prompt_without_profile_uses_project_default(self, builder: str) -> None:
        """The reported bug: no FK + a project default must resolve, not raise."""
        psh, _ = _deps()

        _context, cb_kwargs = _call(
            psh,
            builder,
            profile_manager_id=None,
            prompt_profile=None,
            default_profile=_make_profile(PROJECT_DEFAULT_ID),
        )

        assert cb_kwargs["profile_manager_id"] == PROJECT_DEFAULT_ID, (
            "A prompt with no profile FK must fall back to the project default; "
            "this raised DefaultProfileError before the fix"
        )

    def test_prompt_fk_wins_over_project_default(self, builder: str) -> None:
        """The fallback must not override a profile the prompt already has."""
        psh, _ = _deps()

        _context, cb_kwargs = _call(
            psh,
            builder,
            profile_manager_id=None,
            prompt_profile=_make_profile(PROMPT_FK_ID),
            default_profile=_make_profile(PROJECT_DEFAULT_ID),
        )

        assert cb_kwargs["profile_manager_id"] == PROMPT_FK_ID

    def test_explicit_id_wins_over_everything(self, builder: str) -> None:
        psh, _ = _deps()

        _context, cb_kwargs = _call(
            psh,
            builder,
            profile_manager_id=EXPLICIT_ID,
            prompt_profile=_make_profile(PROMPT_FK_ID),
            default_profile=_make_profile(PROJECT_DEFAULT_ID),
        )

        assert cb_kwargs["profile_manager_id"] == EXPLICIT_ID


@pytest.mark.parametrize("builder", ALL_BUILDERS)
class TestResolvedProfileReachesCallback:
    """``cb_kwargs`` must carry the profile used, not the raw argument.

    Passing the argument through lets the callback re-resolve the project
    default (``None`` is its "re-resolve" sentinel), booking output against a
    different profile than the one that produced it. Reverting the fix at
    either call site must fail here.
    """

    def test_callback_records_the_resolved_profile(self, builder: str) -> None:
        psh, _ = _deps()

        _context, cb_kwargs = _call(
            psh,
            builder,
            profile_manager_id=None,
            prompt_profile=None,
            default_profile=_make_profile(PROJECT_DEFAULT_ID),
        )

        assert cb_kwargs["profile_manager_id"] == PROJECT_DEFAULT_ID, (
            "cb_kwargs must record the resolved profile; the raw None argument "
            "makes the callback silently re-resolve the project default"
        )


@pytest.mark.parametrize("builder", ALL_BUILDERS)
class TestUnresolvableProfile:
    def test_no_profile_anywhere_propagates_default_profile_error(
        self, builder: str
    ) -> None:
        """The fallback must not swallow a genuinely unconfigured project."""
        psh, default_profile_error = _deps()

        with pytest.raises(default_profile_error):
            _call(
                psh,
                builder,
                profile_manager_id=None,
                prompt_profile=None,
                default_profile=None,
                default_raises=default_profile_error(),
            )


class TestSynchronousFetchResponse:
    """``_fetch_response`` carries the same fallback and is still live.

    It is reached from ``fetch_response`` (the non-dispatch branch) and returns
    a service response rather than ``cb_kwargs``, so the resolved profile is
    observed where it is first consumed: ``validate_adapter_status``.
    """

    def _resolved_profile(
        self,
        psh: Any,
        *,
        profile_manager_id: str | None,
        prompt_profile: Any,
        default_profile: Any,
    ) -> Any:
        helper = psh.PromptStudioHelper
        seen: list[Any] = []

        def _get_explicit(profile_manager_id: str) -> Any:
            assert profile_manager_id == EXPLICIT_ID
            return _make_profile(EXPLICIT_ID)

        patches = [
            patch.object(
                psh.ProfileManager,
                "get_default_llm_profile",
                autospec=True,
                side_effect=lambda tool: default_profile,
            ),
            patch.object(
                psh.ProfileManagerHelper,
                "get_profile_manager",
                autospec=True,
                side_effect=lambda profile_manager_id: _get_explicit(profile_manager_id),
            ),
            patch.object(
                helper,
                "validate_adapter_status",
                autospec=True,
                side_effect=seen.append,
            ),
            patch.object(
                helper, "validate_profile_manager_owner_access", autospec=True
            ),
            patch.object(
                helper, "_resolve_llm_ids", autospec=True, return_value=("m", "c")
            ),
            # Stop the call once the profile has been observed; everything past
            # this point needs storage and an LLM.
            patch.object(psh, "EnvHelper", MagicMock(side_effect=RuntimeError)),
        ]
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with pytest.raises(Exception):  # noqa: B017 - halted deliberately
                helper._fetch_response(
                    tool=MagicMock(tool_id="tool-1", summarize_as_source=False),
                    doc_path="/docs/a.pdf",
                    doc_name="a.pdf",
                    prompt=_make_prompt(prompt_profile),
                    org_id="org-1",
                    document_id="doc-1",
                    run_id="run-1",
                    user_id="user-1",
                    profile_manager_id=profile_manager_id,
                    request_user=None,
                )

        assert seen, "validate_adapter_status was never reached"
        return seen[0]

    def test_prompt_without_profile_uses_project_default(self) -> None:
        """The reported bug, on the synchronous path."""
        psh, _ = _deps()

        resolved = self._resolved_profile(
            psh,
            profile_manager_id=None,
            prompt_profile=None,
            default_profile=_make_profile(PROJECT_DEFAULT_ID),
        )

        assert str(resolved.profile_id) == PROJECT_DEFAULT_ID

    def test_prompt_fk_wins_over_project_default(self) -> None:
        psh, _ = _deps()

        resolved = self._resolved_profile(
            psh,
            profile_manager_id=None,
            prompt_profile=_make_profile(PROMPT_FK_ID),
            default_profile=_make_profile(PROJECT_DEFAULT_ID),
        )

        assert str(resolved.profile_id) == PROMPT_FK_ID


class TestSynchronousOutputAttribution:
    """``_execute_single_prompt`` must book output against the profile used.

    The async builders record the resolved profile in ``cb_kwargs``; the
    synchronous path hands ``profile_manager_id`` to ``_handle_response``, whose
    ``None`` branch re-resolves the project default. A prompt carrying its own
    FK would then run under the FK but store its output under the project
    default.
    """

    def _handled_profile_id(
        self, psh: Any, *, profile_manager_id: str | None, prompt_profile: Any
    ) -> Any:
        helper = psh.PromptStudioHelper
        prompt = _make_prompt(prompt_profile)
        prompt.enforce_type = "Text"
        prompt.tool_id = MagicMock(tool_id="tool-1")
        seen: dict[str, Any] = {}

        patches = [
            patch.object(
                helper, "_fetch_prompt_from_id", autospec=True, return_value=prompt
            ),
            patch.object(
                helper, "_fetch_response", autospec=True, return_value={"status": "OK"}
            ),
            patch.object(helper, "_publish_log", autospec=True),
            patch.object(
                psh.ProfileManager,
                "get_default_llm_profile",
                autospec=True,
                side_effect=lambda tool: _make_profile(PROJECT_DEFAULT_ID),
            ),
            patch.object(
                psh.ProfileManagerHelper,
                "get_profile_manager",
                autospec=True,
                side_effect=lambda profile_manager_id: _make_profile(profile_manager_id),
            ),
            patch.object(
                helper,
                "_handle_response",
                autospec=True,
                side_effect=lambda **kw: seen.update(kw),
            ),
            patch.object(psh, "get_plugin", MagicMock(return_value=None)),
        ]
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            helper._execute_single_prompt(
                id="prompt-1",
                doc_path="/docs/a.pdf",
                doc_name="a.pdf",
                tool_id="tool-1",
                org_id="org-1",
                user_id="user-1",
                document_id="doc-1",
                run_id="run-1",
                profile_manager_id=profile_manager_id,
                request_user=None,
            )

        assert seen, "_handle_response was never reached"
        return seen["profile_manager_id"]

    def test_prompt_fk_is_recorded_not_reresolved(self) -> None:
        psh, _ = _deps()

        recorded = self._handled_profile_id(
            psh, profile_manager_id=None, prompt_profile=_make_profile(PROMPT_FK_ID)
        )

        assert recorded == PROMPT_FK_ID, (
            "Output must be booked against the prompt's own profile; passing "
            "None makes _handle_response re-resolve the project default"
        )

    def test_project_default_is_recorded_when_no_fk(self) -> None:
        psh, _ = _deps()

        recorded = self._handled_profile_id(
            psh, profile_manager_id=None, prompt_profile=None
        )

        assert recorded == PROJECT_DEFAULT_ID

    def test_explicit_id_round_trips(self) -> None:
        """The explicit rung is a pass-through, but must stay one."""
        psh, _ = _deps()

        recorded = self._handled_profile_id(
            psh,
            profile_manager_id=EXPLICIT_ID,
            prompt_profile=_make_profile(PROMPT_FK_ID),
        )

        assert recorded == EXPLICIT_ID


def test_default_profile_error_is_a_client_error() -> None:
    """A missing default profile is user-fixable configuration, not a 500."""
    _psh, default_profile_error = _deps()

    assert default_profile_error.status_code == 400
    detail = str(default_profile_error.default_detail).lower()
    assert "project" in detail and "prompt" in detail, (
        "The message must name both places a profile can come from; it is also "
        "raised for monitor/challenge resolution, not just the prompt"
    )
