"""Regression tests for ``PromptStudioRegistryHelper.frame_export_json``.

Pins the UN-3332 fix: when ``tool.single_pass_extraction_mode`` is True,
single-pass execution stores ``PromptStudioOutputManager`` rows under the
tool's *default* profile with ``is_single_pass_extract=True`` (see
``OutputManagerHelper.handle_prompt_output_update``). The export
validator must therefore look up rows by that same (profile, mode) tuple
-- previously it filtered by ``prompt.profile_manager`` (the prompt-card
FK, frozen at prompt-creation time), which silently missed rows whenever
the default profile and the prompt-level profile diverged. The result
was a misleading "project without prompts cannot be exported" error
after a successful single-pass run.

The same resolved profile must also drive the per-prompt export entry
(llm / vector-db / embedding / x2text / chunking / retrieval settings),
so the exported tool carries the settings the prompts actually ran with.

The helper module is imported for real and its collaborators are patched
on it per-test, so no database is touched. Nothing is stubbed into
``sys.modules``: that pattern shadows the real ``account_v2`` /
``unstract.*`` modules for every later test on the same pytest worker
(see ``b60dd6f3``). Like the sibling ``test_fetch_json_for_registry``,
this file needs Django configured -- it runs in the rig's
``unit-backend`` tier, where ``DJANGO_SETTINGS_MODULE`` is set
(``tests/groups.yaml``).
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_registry_v2 import (
    prompt_studio_registry_helper as _psrh_mod,
)

PromptStudioRegistryHelper = _psrh_mod.PromptStudioRegistryHelper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(name: str) -> MagicMock:
    """Build a ProfileManager mock with the attributes frame_export_json
    accesses on both the default and prompt-level profiles.
    """
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


def _run_export(
    *,
    tool: MagicMock,
    prompt: MagicMock,
    default_profile: MagicMock,
    force_export: bool = False,
) -> tuple[MagicMock, Any]:
    """Invoke ``frame_export_json`` with every collaborator patched on the
    helper module and return the captured ``PromptStudioOutputManager``
    filter call along with the result.
    """
    # The filter chain is ``Model.objects.filter(...).all()`` -- return a
    # truthy list so the prompt is treated as "run".
    output_manager = MagicMock(name="PromptStudioOutputManager")
    filter_call = output_manager.objects.filter
    filter_call.return_value.all.return_value = [object()]

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(_psrh_mod, "PromptStudioOutputManager", output_manager)
        )
        stack.enter_context(
            patch.object(
                _psrh_mod.ProfileManager,
                "get_default_llm_profile",
                return_value=default_profile,
            )
        )
        stack.enter_context(
            patch.object(
                _psrh_mod, "validate_lookups_for_export", return_value=({}, None)
            )
        )
        stack.enter_context(patch.object(_psrh_mod, "get_plugin", return_value=None))
        result = PromptStudioRegistryHelper.frame_export_json(
            tool=tool, prompts=[prompt], force_export=force_export
        )

    return filter_call, result


def _per_prompt_output(result: Any) -> dict[str, Any]:
    """Return the single per-prompt entry from a frame_export_json result."""
    outputs = result["outputs"]
    assert len(outputs) == 1, f"expected exactly one per-prompt output, got {outputs!r}"
    return outputs[0]


def _assert_output_uses_profile(output: dict[str, Any], profile: MagicMock) -> None:
    """Assert the per-prompt export entry was assembled from ``profile``.

    Covers the fields the exported tool consumes when single-pass is
    disabled at runtime -- these were previously hardcoded to
    ``prompt.profile_manager`` regardless of single-pass mode.
    """
    assert output["llm"] == profile.llm.id
    assert output["vector-db"] == profile.vector_store.id
    assert output["embedding"] == profile.embedding_model.id
    assert output["x2text_adapter"] == profile.x2text.id
    assert output["chunk-size"] == profile.chunk_size
    assert output["chunk-overlap"] == profile.chunk_overlap
    assert output["retrieval-strategy"] == profile.retrieval_strategy
    assert output["similarity-top-k"] == profile.similarity_top_k
    assert output["section"] == profile.section
    assert output["reindex"] == profile.reindex


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFrameExportJsonProfileLookup:
    """Pin the UN-3332 fix: validation profile depends on single-pass mode."""

    def test_single_pass_uses_default_profile_and_single_pass_flag(self) -> None:
        """When single-pass is on, BOTH the validation filter and the
        per-prompt export entry must use the tool's default profile (with
        ``is_single_pass_extract=True``) -- NOT the prompt's own
        ``profile_manager`` FK.
        """
        default_profile = _make_profile("default")
        prompt_profile = _make_profile("prompt")  # the "wrong" one
        tool = _make_tool(single_pass=True)
        prompt = _make_prompt(profile=prompt_profile)

        filter_call, result = _run_export(
            tool=tool, prompt=prompt, default_profile=default_profile
        )

        filter_call.assert_called_once()
        kwargs = filter_call.call_args.kwargs
        assert (
            kwargs["profile_manager"] is default_profile
        ), "single-pass export must validate against the default profile"
        assert kwargs["is_single_pass_extract"] is True
        assert kwargs["tool_id"] == tool.tool_id
        assert kwargs["prompt_id"] == prompt.prompt_id
        _assert_output_uses_profile(_per_prompt_output(result), default_profile)

    def test_non_single_pass_uses_prompt_profile_and_normal_flag(self) -> None:
        """When single-pass is off, BOTH the validation filter and the
        per-prompt export entry must use the prompt's own
        ``profile_manager`` (with ``is_single_pass_extract=False``).
        """
        default_profile = _make_profile("default")
        prompt_profile = _make_profile("prompt")
        tool = _make_tool(single_pass=False)
        prompt = _make_prompt(profile=prompt_profile)

        filter_call, result = _run_export(
            tool=tool, prompt=prompt, default_profile=default_profile
        )

        filter_call.assert_called_once()
        kwargs = filter_call.call_args.kwargs
        assert (
            kwargs["profile_manager"] is prompt_profile
        ), "non-single-pass export must validate against the prompt's profile"
        assert kwargs["is_single_pass_extract"] is False
        _assert_output_uses_profile(_per_prompt_output(result), prompt_profile)

    def test_force_export_skips_output_lookup_entirely(self) -> None:
        """``force_export=True`` bypasses validation: the filter must
        never be called. Per-prompt JSON still follows single-pass mode
        (default profile here, because ``single_pass=True``).
        """
        default_profile = _make_profile("default")
        prompt_profile = _make_profile("prompt")
        tool = _make_tool(single_pass=True)
        prompt = _make_prompt(profile=prompt_profile)

        filter_call, result = _run_export(
            tool=tool,
            prompt=prompt,
            default_profile=default_profile,
            force_export=True,
        )

        filter_call.assert_not_called()
        _assert_output_uses_profile(_per_prompt_output(result), default_profile)
