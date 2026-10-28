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


_BEDROCK_ID = "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"
_BEDROCK_META = {
    "model": "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "aws_region_name": "us-east-1",
}


def _summary(pages: int) -> str:
    from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
        LLMWhispererHelper,
    )

    return LLMWhispererHelper.build_image_output_summary([MagicMock()] * pages)


class TestCachedImageExtractionIsRecheckedForTheLLM:
    """A cache hit made for another LLM must still fit this profile's LLM.

    The extraction cache key ignores the LLM; after a profile switches from
    a generous model to Bedrock Claude (20 images), a cache hit would skip
    the page budget and the prompt would fail at the provider.
    """

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VLM_IMAGE_ANSWER_PAGE_CAP", raising=False)
        monkeypatch.delenv("VLM_IMAGE_LIMITS_ENFORCE", raising=False)

    @staticmethod
    def _cache_hit(monkeypatch: pytest.MonkeyPatch, pages: int) -> MagicMock:
        profile = MagicMock(name="ProfileManager")
        profile.x2text.adapter_id = _LLMW
        profile.x2text.metadata = {"output_mode": "image"}
        profile.x2text.id = "x2t-1"
        profile.llm.id = "llm-bedrock"
        profile.llm.adapter_id = _BEDROCK_ID
        profile.llm.metadata = _BEDROCK_META
        index_helper = MagicMock(name="PromptStudioIndexHelper")
        index_helper.check_extraction_status.return_value = True
        monkeypatch.setattr(_psh_mod, "PromptStudioIndexHelper", index_helper)
        storage = MagicMock()
        storage.read.return_value = _summary(pages)
        monkeypatch.setattr(
            _psh_mod.EnvHelper, "get_storage", MagicMock(return_value=storage)
        )
        dispatcher = MagicMock()
        monkeypatch.setattr(
            PromptStudioHelper, "_get_dispatcher", MagicMock(return_value=dispatcher)
        )
        return profile

    @staticmethod
    def _extract(profile: MagicMock) -> str:
        return PromptStudioHelper.dynamic_extractor(
            file_path="/data/doc.pdf",
            enable_highlight=False,
            run_id="r1",
            org_id="org1",
            profile_manager=profile,
            document_id="doc1",
        )

    def test_over_budget_cache_hit_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = self._cache_hit(monkeypatch, pages=50)
        with pytest.raises(_psh_mod.ExtractionAPIError) as excinfo:
            self._extract(profile)
        msg = str(excinfo.value)
        assert "IMAGE_PAGE_CAP_EXCEEDED: This document has 50 pages" in msg
        assert "Amazon Bedrock" in msg

    def test_cache_hit_within_budget_is_served(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = self._cache_hit(monkeypatch, pages=20)
        assert self._extract(profile) == _summary(20)

    def test_enforce_switch_off_applies_the_fixed_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Switched off, the cache hit is checked against the fixed 90-page
        # cap instead of the LLM's 20: 50 pages pass, 91 are rejected.
        monkeypatch.setenv("VLM_IMAGE_LIMITS_ENFORCE", "false")
        monkeypatch.delenv("VLM_IMAGE_ANSWER_PAGE_CAP", raising=False)
        profile = self._cache_hit(monkeypatch, pages=50)
        assert self._extract(profile) == _summary(50)
        profile = self._cache_hit(monkeypatch, pages=91)
        with pytest.raises(_psh_mod.ExtractionAPIError) as excinfo:
            self._extract(profile)
        msg = str(excinfo.value)
        assert "IMAGE_PAGE_CAP_EXCEEDED" in msg
        assert "It has 91 pages, and the limit is 90" in msg

    def test_summary_page_count_round_trips(self) -> None:
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
            LLMWhispererHelper,
        )

        parse = LLMWhispererHelper.page_count_from_image_output_summary
        assert parse(_summary(1)) == 1
        assert parse(_summary(321)) == 321
        assert parse("ordinary extracted text") is None
        assert parse(None) is None

    # Today's summary text, written out: extracts already cached carry it, so
    # a format change must keep parsing these.
    _ONE_PAGE = (
        "[LLMWhisperer image output mode] 1 page image extracted from the PDF "
        "and stored in FileStorage. Per-page references are available in the "
        "page_images extraction metadata."
    )
    _21_PAGES = (
        "[LLMWhisperer image output mode] 21 page images extracted from the PDF "
        "and stored in FileStorage. Per-page references are available in the "
        "page_images extraction metadata."
    )

    def test_cached_summary_literals_parse(self) -> None:
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
            LLMWhispererHelper,
        )

        parse = LLMWhispererHelper.page_count_from_image_output_summary
        assert parse(self._ONE_PAGE) == 1
        assert parse(self._21_PAGES) == 21

    def test_cached_21_page_literal_is_rejected_for_bedrock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = self._cache_hit(monkeypatch, pages=1)
        with pytest.raises(_psh_mod.ExtractionAPIError) as excinfo:
            PromptStudioHelper._check_cached_image_extraction(
                profile, self._21_PAGES, "doc.pdf"
            )
        msg = str(excinfo.value)
        assert "IMAGE_PAGE_CAP_EXCEEDED: This document has 21 pages" in msg
        assert "Amazon Bedrock" in msg
