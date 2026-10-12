"""Extraction payloads carry the LLM ids whose image limits apply (UN-4427).

The executor checks an image-mode document against the limits of the LLM
that will read it before LLMWhisperer bills the conversion, so every
Prompt Studio extract payload names that LLM.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod
from prompt_studio.prompt_studio_core_v2.tests.test_build_index_payload import (
    _dispatch_build,
    _make_profile,
)

PromptStudioHelper = _psh_mod.PromptStudioHelper
IKeys = _psh_mod.IKeys
_LLMW = "llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93"


def test_constant_matches_the_executor_key() -> None:
    assert IKeys.LLM_INSTANCE_IDS == "llm_instance_ids"


class TestIndexPayload:
    def test_extract_params_name_the_default_profile_llm(self) -> None:
        profile = _make_profile()
        profile.llm.id = "llm-default"
        context, *_ = _dispatch_build(check_return=False, read_return="", profile=profile)
        extract = context.executor_params["extract_params"]
        assert extract[IKeys.LLM_INSTANCE_IDS] == ["llm-default"]

    def test_profile_without_llm_sends_an_empty_list(self) -> None:
        profile = _make_profile()
        profile.llm = None
        context, *_ = _dispatch_build(check_return=False, read_return="", profile=profile)
        assert context.executor_params["extract_params"][IKeys.LLM_INSTANCE_IDS] == []


class TestDynamicExtractorPayload:
    def test_payload_names_the_running_profile_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = MagicMock(name="ProfileManager")
        profile.x2text.adapter_id = _LLMW
        profile.x2text.metadata = {"output_mode": "image"}
        profile.x2text.id = "x2t-1"
        profile.llm.id = "llm-override"
        index_helper = MagicMock(name="PromptStudioIndexHelper")
        index_helper.check_extraction_status.return_value = False
        index_helper.mark_extraction_status.return_value = (
            _psh_mod.ExtractionStatusResult.OK
        )
        monkeypatch.setattr(_psh_mod, "PromptStudioIndexHelper", index_helper)
        monkeypatch.setattr(_psh_mod, "StateStore", MagicMock())
        monkeypatch.setattr(
            _psh_mod.EnvHelper, "get_storage", MagicMock(return_value=MagicMock())
        )
        monkeypatch.setattr(
            PromptStudioHelper, "_get_platform_api_key", MagicMock(return_value="k")
        )
        monkeypatch.setattr(
            _psh_mod, "invalidate_vlm_answers_on_reextraction", MagicMock()
        )
        dispatcher = MagicMock()
        dispatcher.dispatch.return_value = MagicMock(
            success=True, data={"extracted_text": "pages"}
        )
        monkeypatch.setattr(
            PromptStudioHelper, "_get_dispatcher", MagicMock(return_value=dispatcher)
        )

        PromptStudioHelper.dynamic_extractor(
            file_path="/data/doc.pdf",
            enable_highlight=False,
            run_id="r1",
            org_id="org1",
            profile_manager=profile,
            document_id="doc1",
        )

        context = dispatcher.dispatch.call_args.args[0]
        assert context.executor_params[IKeys.LLM_INSTANCE_IDS] == ["llm-override"]
