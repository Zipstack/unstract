"""Regression tests: ``build_single_pass_payload`` stamps the x2text output mode.

The executor's single-pass guard trusts the payload stamp — an unstamped IDE
payload is treated as a pre-upgrade text-mode run and the guard never fires.
``build_single_pass_payload`` was the one payload builder that skipped
``_stamp_x2text_output_mode``, which made image-mode + single-pass answer
every prompt against the one-line extraction summary, silently. These tests
pin the stamp into the built ``tool_settings`` so deleting the call fails.

Unit tests: the real helper module is imported (Django is loaded by the rig's
test env) and every collaborator is patched on it per-test, so no database is
touched.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod
from prompt_studio.prompt_studio_core_v2.constants import ToolStudioPromptKeys as TSPKeys

PromptStudioHelper = _psh_mod.PromptStudioHelper

_LLMW_ADAPTER_ID = "llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93"


def _make_tool():
    tool = MagicMock(name="CustomTool")
    tool.tool_id = "tool-1"
    tool.prompt_grammer = None
    tool.challenge_llm = None
    tool.enable_challenge = False
    tool.enable_highlight = False
    tool.enable_word_confidence = False
    tool.summarize_as_source = False
    tool.custom_data = None
    return tool


def _make_profile(metadata: dict | None, adapter_id: str = _LLMW_ADAPTER_ID):
    profile = MagicMock(name="ProfileManager")
    profile.x2text.id = "x2t-1"
    profile.x2text.adapter_id = adapter_id
    profile.x2text.metadata = metadata
    profile.llm.id = "llm-1"
    profile.embedding_model.id = "emb-1"
    profile.vector_store.id = "vdb-1"
    profile.chunk_overlap = 64
    profile.retrieval_strategy = "simple"
    profile.similarity_top_k = 3
    profile.profile_id = "profile-1"
    return profile


def _make_prompt():
    p = MagicMock(name="ToolStudioPrompt")
    p.prompt = "What is the total?"
    p.active = True
    p.enforce_type = "text"
    p.prompt_key = "total"
    p.prompt_id = "p-1"
    return p


def _build(profile) -> dict:
    """Run ``build_single_pass_payload`` with collaborators patched.

    Returns the ``tool_settings`` dict from the built executor payload.
    """
    fs_instance = MagicMock(name="fs_instance")
    fs_instance.get_hash_from_file.return_value = "hash-1"

    with ExitStack() as stack:
        for target, attr, value in (
            (
                _psh_mod.ProfileManager,
                "get_default_llm_profile",
                MagicMock(return_value=profile),
            ),
            (PromptStudioHelper, "validate_adapter_status", MagicMock(return_value=None)),
            (
                PromptStudioHelper,
                "validate_profile_manager_owner_access",
                MagicMock(return_value=None),
            ),
            (PromptStudioHelper, "dynamic_extractor", MagicMock(return_value=None)),
            (
                PromptStudioHelper,
                "_get_platform_api_key",
                MagicMock(return_value="pk-test"),
            ),
            (_psh_mod.EnvHelper, "get_storage", MagicMock(return_value=fs_instance)),
            (_psh_mod, "get_lookup_configs_for_tool", MagicMock(return_value=None)),
            (_psh_mod.StateStore, "get", MagicMock(return_value="")),
        ):
            stack.enter_context(patch.object(target, attr, value))

        context, _cb_kwargs = PromptStudioHelper.build_single_pass_payload(
            tool=_make_tool(),
            doc_path="/data/org/user/tool/statement.pdf",
            doc_name="statement.pdf",
            prompts=[_make_prompt()],
            org_id="org-1",
            user_id="user-1",
            document_id="doc-1",
            run_id="run-1",
            request_user=MagicMock(name="request-user"),
        )
        return context.executor_params[TSPKeys.TOOL_SETTINGS]


class TestSinglePassPayloadStampsOutputMode:
    def test_image_mode_profile_is_stamped_into_tool_settings(self) -> None:
        # The executor's single-pass guard fires only on this stamp for IDE
        # payloads — without it, image mode + single-pass silently answers
        # from the one-line extraction summary.
        tool_settings = _build(_make_profile({"output_mode": "image"}))
        assert tool_settings[TSPKeys.X2TEXT_OUTPUT_MODE] == "image"

    def test_text_mode_profile_is_stamped_into_tool_settings(self) -> None:
        # A stamped non-image mode must also be present (stamp != image-only):
        # the executor trusts stamp presence to skip live resolution entirely.
        tool_settings = _build(_make_profile({"output_mode": "layout_preserving"}))
        assert tool_settings[TSPKeys.X2TEXT_OUTPUT_MODE] == "layout_preserving"

    def test_non_llmwhisperer_adapter_is_not_stamped(self) -> None:
        tool_settings = _build(
            _make_profile({"output_mode": "image"}, adapter_id="some-other|123")
        )
        assert TSPKeys.X2TEXT_OUTPUT_MODE not in tool_settings
