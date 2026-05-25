"""Regression tests for ``PromptStudioRegistryHelper.frame_export_json``.

Pins the UN-3332 fix: when ``tool.single_pass_extraction_mode`` is True,
single-pass execution stores ``PromptStudioOutputManager`` rows under the
tool's *default* profile with ``is_single_pass_extract=True`` (see
``OutputManagerHelper.handle_prompt_output_update``). The export
validator must therefore look up rows by that same (profile, mode) tuple
— previously it filtered by ``prompt.profile_manager`` (the prompt-card
FK, frozen at prompt-creation time), which silently missed rows whenever
the default profile and the prompt-level profile diverged. The result
was a misleading "project without prompts cannot be exported" error
after a successful single-pass run.

Mirrors the ``test_build_index_payload`` approach: the backend test
environment has no ``pytest-django`` and the helper has a heavy
Django-coupled import surface, so every collaborator is stubbed on
``sys.modules`` before the helper is imported.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _install(name: str, attrs: dict[str, Any] | None = None) -> types.ModuleType:
    """Install (or replace) a fake module into ``sys.modules``."""
    mod = types.ModuleType(name)
    if attrs:
        for key, value in attrs.items():
            setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _install_package(name: str) -> types.ModuleType:
    """Install a fake package (only if it is not already loaded)."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


try:
    # Configure a minimal Django settings module so that ``settings``
    # attribute access inside ``frame_export_json`` (PLATFORM_POSTAMBLE,
    # WORD_CONFIDENCE_POSTAMBLE) does not raise ``ImproperlyConfigured``.
    # Safe to call repeatedly — ``configure`` is idempotent for our use
    # because we check ``configured`` first.
    try:
        from django.conf import settings as _dj_settings

        if not _dj_settings.configured:
            _dj_settings.configure(
                PLATFORM_POSTAMBLE="",
                WORD_CONFIDENCE_POSTAMBLE="",
            )
    except Exception:
        pass

    _install_package("account_v2")
    _install("account_v2.models", {"User": MagicMock(name="User")})

    _install_package("adapter_processor_v2")
    _install(
        "adapter_processor_v2.models",
        {"AdapterInstance": MagicMock(name="AdapterInstance")},
    )

    _install("plugins", {"get_plugin": MagicMock(return_value=None)})

    _install_package("prompt_studio")
    _install(
        "prompt_studio.lookup_utils",
        {"validate_lookups_for_export": MagicMock(return_value=({}, None))},
    )

    _install_package("prompt_studio.prompt_profile_manager_v2")
    _install(
        "prompt_studio.prompt_profile_manager_v2.models",
        {"ProfileManager": MagicMock(name="ProfileManager")},
    )

    _install_package("prompt_studio.prompt_studio_core_v2")
    _install(
        "prompt_studio.prompt_studio_core_v2.models",
        {"CustomTool": MagicMock(name="CustomTool")},
    )
    _install(
        "prompt_studio.prompt_studio_core_v2.prompt_studio_helper",
        {"PromptStudioHelper": MagicMock(name="PromptStudioHelper")},
    )

    _install_package("prompt_studio.prompt_studio_output_manager_v2")
    _install(
        "prompt_studio.prompt_studio_output_manager_v2.models",
        {"PromptStudioOutputManager": MagicMock(name="PromptStudioOutputManager")},
    )

    _install_package("prompt_studio.prompt_studio_v2")
    _install(
        "prompt_studio.prompt_studio_v2.models",
        {"ToolStudioPrompt": MagicMock(name="ToolStudioPrompt")},
    )

    _install_package("unstract")
    _install_package("unstract.tool_registry")
    _install(
        "unstract.tool_registry.dto",
        {
            "Properties": MagicMock(name="Properties"),
            "Spec": MagicMock(name="Spec"),
            "Tool": MagicMock(name="Tool"),
        },
    )

    # Sibling modules of the helper — both define Django Model /
    # ModelSerializer classes that require ``INSTALLED_APPS`` at import
    # time. Stub them so the helper's ``from .models import ...`` and
    # ``from .serializers import ...`` resolve without booting Django.
    _install(
        "prompt_studio.prompt_studio_registry_v2.models",
        {"PromptStudioRegistry": MagicMock(name="PromptStudioRegistry")},
    )
    _install(
        "prompt_studio.prompt_studio_registry_v2.serializers",
        {"PromptStudioRegistrySerializer": MagicMock(name="PromptStudioRegistrySerializer")},
    )

    from prompt_studio.prompt_studio_registry_v2 import (  # noqa: E402
        prompt_studio_registry_helper as _psrh_mod,
    )

    PromptStudioRegistryHelper = _psrh_mod.PromptStudioRegistryHelper
    _IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover — environment guard
    _IMPORT_ERROR = (
        f"prompt_studio_registry_helper could not be imported in this "
        f"environment: {type(exc).__name__}: {exc}"
    )
    PromptStudioRegistryHelper = None  # type: ignore[assignment]
    _psrh_mod = None  # type: ignore[assignment]


pytestmark = pytest.mark.skipif(
    _IMPORT_ERROR is not None, reason=_IMPORT_ERROR or ""
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(name: str) -> MagicMock:
    """Build a ProfileManager mock with the attributes frame_export_json
    accesses on both the default and prompt-level profiles."""
    profile = MagicMock(name=f"ProfileManager[{name}]")
    profile.profile_id = f"profile-{name}"
    profile.llm.id = f"llm-{name}"
    profile.vector_store.id = f"vdb-{name}"
    profile.embedding_model.id = f"emb-{name}"
    profile.embedding_model.adapter_id = f"adapter-{name}|suffix"
    profile.x2text.id = f"x2t-{name}"
    profile.chunk_size = 512
    profile.chunk_overlap = 64
    profile.retrieval_strategy = "simple"
    profile.similarity_top_k = 3
    profile.section = "all"
    profile.reindex = False
    return profile


def _make_tool(*, single_pass: bool) -> MagicMock:
    tool = MagicMock(name="CustomTool")
    tool.tool_id = "tool-1"
    tool.tool_name = "test-tool"
    tool.description = "desc"
    tool.author = "author"
    tool.prompt_grammer = None
    tool.summarize_prompt = ""
    tool.summarize_as_source = False
    tool.preamble = ""
    tool.postamble = ""
    tool.enable_challenge = False
    tool.challenge_llm = None
    tool.single_pass_extraction_mode = single_pass
    tool.enable_highlight = False
    tool.enable_word_confidence = False
    return tool


def _make_prompt(*, profile: MagicMock) -> MagicMock:
    prompt = MagicMock(name="ToolStudioPrompt")
    prompt.prompt_id = "prompt-1"
    prompt.prompt_key = "key"
    prompt.prompt = "what is X?"
    prompt.prompt_type = "LLM"  # any non-NOTES value
    prompt.active = True
    prompt.required = False
    prompt.enforce_type = "text"
    prompt.profile_manager = profile
    prompt.enable_postprocessing_webhook = False
    prompt.postprocessing_webhook_url = ""
    return prompt


def _run_export(*, tool: MagicMock, prompt: MagicMock, force_export: bool = False):
    """Invoke ``frame_export_json`` with a patched
    ``PromptStudioOutputManager.objects.filter`` and return the captured
    filter call along with the result (or raised exception).
    """
    # The filter chain is ``Model.objects.filter(...).all()`` — return a
    # truthy list so the prompt is treated as "run".
    filter_call = MagicMock(name="filter")
    filter_call.return_value.all.return_value = [object()]

    objects = MagicMock(name="objects")
    objects.filter = filter_call

    raised: Exception | None = None
    result: Any = None
    with patch.object(_psrh_mod.PromptStudioOutputManager, "objects", objects):
        try:
            result = PromptStudioRegistryHelper.frame_export_json(
                tool=tool, prompts=[prompt], force_export=force_export,
            )
        except Exception as exc:  # surface to assertions
            raised = exc

    return filter_call, result, raised


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFrameExportJsonProfileLookup:
    """Pin the UN-3332 fix: validation profile depends on single-pass mode."""

    def test_single_pass_uses_default_profile_and_single_pass_flag(self) -> None:
        """When single-pass is on, filter must use the tool's default
        profile and ``is_single_pass_extract=True`` — NOT the prompt's
        own profile_manager FK.
        """
        default_profile = _make_profile("default")
        prompt_profile = _make_profile("prompt")  # the "wrong" one
        tool = _make_tool(single_pass=True)
        prompt = _make_prompt(profile=prompt_profile)

        with patch.object(
            _psrh_mod.ProfileManager,
            "get_default_llm_profile",
            return_value=default_profile,
        ):
            filter_call, _result, raised = _run_export(tool=tool, prompt=prompt)

        assert raised is None, f"export failed unexpectedly: {raised!r}"
        filter_call.assert_called_once()
        kwargs = filter_call.call_args.kwargs
        assert kwargs["profile_manager"] is default_profile, (
            "single-pass export must validate against the default profile"
        )
        assert kwargs["is_single_pass_extract"] is True
        assert kwargs["tool_id"] == tool.tool_id
        assert kwargs["prompt_id"] == prompt.prompt_id

    def test_non_single_pass_uses_prompt_profile_and_normal_flag(self) -> None:
        """When single-pass is off, filter must use the prompt's own
        ``profile_manager`` and ``is_single_pass_extract=False``.
        """
        default_profile = _make_profile("default")
        prompt_profile = _make_profile("prompt")
        tool = _make_tool(single_pass=False)
        prompt = _make_prompt(profile=prompt_profile)

        with patch.object(
            _psrh_mod.ProfileManager,
            "get_default_llm_profile",
            return_value=default_profile,
        ):
            filter_call, _result, raised = _run_export(tool=tool, prompt=prompt)

        assert raised is None, f"export failed unexpectedly: {raised!r}"
        filter_call.assert_called_once()
        kwargs = filter_call.call_args.kwargs
        assert kwargs["profile_manager"] is prompt_profile, (
            "non-single-pass export must validate against the prompt's profile"
        )
        assert kwargs["is_single_pass_extract"] is False

    def test_force_export_skips_output_lookup_entirely(self) -> None:
        """``force_export=True`` bypasses validation: the filter must
        never be called.
        """
        default_profile = _make_profile("default")
        prompt_profile = _make_profile("prompt")
        tool = _make_tool(single_pass=True)
        prompt = _make_prompt(profile=prompt_profile)

        with patch.object(
            _psrh_mod.ProfileManager,
            "get_default_llm_profile",
            return_value=default_profile,
        ):
            filter_call, _result, raised = _run_export(
                tool=tool, prompt=prompt, force_export=True,
            )

        assert raised is None, f"forced export failed: {raised!r}"
        filter_call.assert_not_called()
