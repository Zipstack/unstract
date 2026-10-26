"""Unit tests for the upload-time page-cap check in image output mode.

Image mode sends every page to the LLM in one request, so a PDF over the page
cap can never be answered. The check rejects it at upload, before anything is
stored, but only when the project's default profile is LLMWhisperer in image
mode — the same document is fine in a text mode.

Unit tests: the profile is a lightweight mock and the PDFs are generated in
memory, so no database or storage is touched.
"""

from __future__ import annotations

import inspect
import io
import logging
from unittest.mock import MagicMock, patch

import pypdfium2 as pdfium
import pytest

from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod
from prompt_studio.prompt_studio_core_v2 import views as _views_mod
from prompt_studio.prompt_studio_core_v2.exceptions import ImageModePageLimitExceeded

PromptStudioHelper = _psh_mod.PromptStudioHelper
check = PromptStudioHelper.validate_upload_page_count_for_image_mode
gated = PromptStudioHelper.uploads_use_image_output_mode

_LLMW_ADAPTER_ID = "llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93"
_PDF = "application/pdf"


def _profile(metadata: dict | None, adapter_id: str = _LLMW_ADAPTER_ID) -> MagicMock:
    profile = MagicMock(name="ProfileManager")
    profile.x2text.adapter_id = adapter_id
    profile.x2text.metadata = metadata
    return profile


def _pdf(pages: int) -> io.BytesIO:
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(612, 792)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


@pytest.fixture(autouse=True)
def _cap_of_five(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real cap (90) via its env override, so small PDFs exercise it.
    monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "5")


class TestRejectsOverCapInImageMode:
    def test_over_cap_pdf_is_rejected_with_a_clear_message(self) -> None:
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(6), _PDF)
        err = excinfo.value
        assert err.status_code == 400
        msg = str(err.detail)
        assert msg.startswith("This document has too many pages for image output mode.")
        assert "It has 6 pages, and the limit is 5" in msg
        assert "VLM_IMAGE_ANSWER_PAGE_CAP" not in msg

    def test_pdf_at_the_cap_is_accepted(self) -> None:
        check(_pdf(5), _PDF)

    def test_stream_is_rewound_for_storage(self) -> None:
        data = _pdf(3)
        check(data, _PDF)
        assert data.tell() == 0
        assert not data.closed


class TestPagesToExtract:
    """The check counts the pages the profile's 'Pages to extract' selects."""

    @staticmethod
    def _ranged(spec: str) -> MagicMock:
        profile = _profile({"output_mode": "image", "pages_to_extract": spec})
        profile.llm = None  # fixed cap of five
        return profile

    def test_range_within_cap_accepts_a_large_pdf(self) -> None:
        check(_pdf(30), _PDF, self._ranged("1-5"))

    def test_range_over_cap_names_the_selection(self) -> None:
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(30), _PDF, self._ranged("1-10"))
        msg = str(excinfo.value.detail)
        assert "'Pages to extract' selects 10 of this document's 30 pages" in msg
        assert "and the limit is 5" in msg
        assert "This document has" not in msg

    def test_range_selecting_every_page_is_not_named(self) -> None:
        # Same rule as the SDK: the selection is named only when it narrows.
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(30), _PDF, self._ranged("1-"))
        msg = str(excinfo.value.detail)
        assert "selects" not in msg
        assert "It has 30 pages, and the limit is 5" in msg

    def test_count_comes_from_the_sdk_helper(self) -> None:
        with patch.object(
            _psh_mod.LLMWhispererHelper, "selected_page_count", return_value=4
        ) as count:
            assert PromptStudioHelper._selected_page_count(self._ranged("1-4"), 30) == (
                4,
                True,
            )
        assert count.call_args.args[1] == 30

    def test_unreadable_setting_is_logged_without_its_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        profile = MagicMock(name="ProfileManager")
        type(profile.x2text).metadata = property(
            lambda _self: (_ for _ in ()).throw(ValueError("secret-key-material"))
        )
        with caplog.at_level(logging.WARNING):
            count = PromptStudioHelper._selected_page_count(profile, 30)
        # Not a range error: counted whole, logged at ERROR by type only.
        assert count == (30, True)
        assert any(r.levelname == "ERROR" for r in caplog.records)
        assert "ValueError" in caplog.text
        assert "Pages to extract" in caplog.text
        assert "secret-key-material" not in caplog.text

    def test_invalid_setting_is_logged_without_its_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            count = PromptStudioHelper._selected_page_count(self._ranged("5-3"), 30)
        assert count == (30, False)
        assert "PageRangeError" in caplog.text
        assert "5-3" not in caplog.text

    def test_invalid_range_falls_back_to_the_whole_document(self) -> None:
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(30), _PDF, self._ranged("5-3"))
        assert "selects" not in str(excinfo.value.detail)
        check(_pdf(5), _PDF, self._ranged("5-3"))

    @pytest.mark.parametrize("with_llm", [False, True], ids=["fixed-cap", "model"])
    def test_invalid_range_never_suggests_a_smaller_range(self, with_llm: bool) -> None:
        profile = self._ranged("0-5")
        if with_llm:
            profile.llm = MagicMock(name="llm")
            profile.llm.adapter_id = "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"
            profile.llm.metadata = {
                "model": "anthropic.claude-sonnet-4-5-20250929-v1:0",
                "aws_region_name": "us-east-1",
            }
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(30), _PDF, profile)
        msg = str(excinfo.value.detail)
        assert "smaller range" not in msg
        assert "'Pages to extract' setting is invalid" in msg
        assert "selects" not in msg


class TestGate:
    def test_image_mode_default_profile_is_gated(self) -> None:
        assert gated(_profile({"output_mode": "image"})) is True

    @pytest.mark.parametrize(
        "metadata", [{"output_mode": "text"}, {"output_mode": "layout_preserving"}, {}]
    )
    def test_text_modes_are_not_gated(self, metadata: dict) -> None:
        assert gated(_profile(metadata)) is False

    def test_other_x2text_adapter_is_not_gated(self) -> None:
        assert gated(_profile({"output_mode": "image"}, adapter_id="other|1")) is False

    def test_no_default_profile_is_not_gated(self) -> None:
        assert gated(None) is False

    def test_profile_without_x2text_is_not_gated(self) -> None:
        profile = MagicMock(name="ProfileManager")
        profile.x2text = None
        assert gated(profile) is False

    def test_unreadable_adapter_metadata_fails_open(self) -> None:
        # e.g. metadata encrypted with a rotated key: uploads must still work.
        profile = MagicMock(name="ProfileManager")
        profile.x2text.adapter_id = _LLMW_ADAPTER_ID
        type(profile.x2text).metadata = property(
            lambda _self: (_ for _ in ()).throw(ValueError("InvalidEncryptionKey"))
        )
        assert gated(profile) is False


class TestPassesThrough:
    def test_non_pdf_is_left_to_the_pdf_only_guard(self) -> None:
        check(io.BytesIO(b"a,b\n"), "text/csv")

    def test_unreadable_pdf_is_left_to_extraction(self) -> None:
        # Extraction re-checks it; a parse failure must not block the upload.
        check(io.BytesIO(b"%PDF-1.7 junk"), _PDF)


class TestCheckIsWiredIntoUpload:
    def test_upload_for_ide_validates_before_storing(self) -> None:
        # Pins the call site and its order: deleting the call, or moving it
        # after the store, fails this test.
        source = inspect.getsource(_views_mod.PromptStudioCoreView.upload_for_ide)
        gate_at = source.index("uploads_use_image_output_mode")
        validate_at = source.index("validate_upload_page_count_for_image_mode")
        store_at = source.index("PromptStudioFileHelper.upload_for_ide")
        assert gate_at < validate_at < store_at


_BEDROCK_ID = "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"
_OPENAI_ID = "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"


def _llm_profile(adapter_id: str, metadata: dict, name: str = "Default") -> MagicMock:
    profile = _profile({"output_mode": "image"})
    profile.profile_name = name
    profile.llm.adapter_id = adapter_id
    profile.llm.metadata = metadata
    return profile


_BEDROCK_META = {
    "model": "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "aws_region_name": "us-east-1",
}
_OPENAI_META = {
    "model": "gpt-5.6",
    "api_key": "k",
    "api_base": "https://api.openai.com/v1",
}


class TestModelAwareUploadCheck:
    """With the default profile's LLM known, the cap is that model's (UN-4427)."""

    @pytest.fixture(autouse=True)
    def _no_env_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VLM_IMAGE_ANSWER_PAGE_CAP", raising=False)

    def test_strict_provider_rejects_below_the_old_fixed_cap(self) -> None:
        profile = _llm_profile(_BEDROCK_ID, _BEDROCK_META, name="Claude on Bedrock")
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(21), _PDF, profile)
        msg = str(excinfo.value.detail)
        assert "This document has 21 pages" in msg
        assert "Amazon Bedrock" in msg and "20 page images" in msg
        assert "default profile" in msg and "Claude on Bedrock" in msg

    def test_strict_provider_accepts_at_its_limit(self) -> None:
        check(_pdf(20), _PDF, _llm_profile(_BEDROCK_ID, _BEDROCK_META))

    def test_generous_provider_accepts_above_the_old_fixed_cap(self) -> None:
        check(_pdf(91), _PDF, _llm_profile(_OPENAI_ID, _OPENAI_META))

    def test_env_ceiling_cannot_raise_the_fixed_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No LLM: the fixed cap. A ceiling above 90 leaves 90 in force.
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "200")
        profile = _profile({"output_mode": "image"})
        profile.llm = None
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(91), _PDF, profile)
        assert "the limit is 90" in str(excinfo.value.detail)

    def test_unresolvable_llm_falls_back_to_the_fixed_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "5")
        profile = _llm_profile("nope|123", {"model": "x"})
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(6), _PDF, profile)
        assert "the limit is 5" in str(excinfo.value.detail)

    def test_validation_error_logs_never_quote_the_metadata(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Missing ``api_base``: pydantic's error quotes the whole stored
        # metadata dict, api_key included.
        canary = "leak-canary"
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "5")
        caplog.set_level(logging.DEBUG)
        profile = _llm_profile(
            "azureopenai|592d84b9-fe03-4102-a17e-6b391f32850b", {"api_key": canary}
        )
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(6), _PDF, profile)
        assert canary not in str(excinfo.value.detail)
        assert "SdkError" in caplog.text
        assert canary not in caplog.text
        assert all(rec.exc_info is None for rec in caplog.records)

    def test_profile_without_llm_uses_the_fixed_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "5")
        profile = _profile({"output_mode": "image"})
        profile.llm = None
        with pytest.raises(ImageModePageLimitExceeded):
            check(_pdf(6), _PDF, profile)

    def test_upload_passes_the_default_profile(self) -> None:
        source = inspect.getsource(_views_mod.PromptStudioCoreView.upload_for_ide)
        call = source[source.index("validate_upload_page_count_for_image_mode") :]
        assert "default_profile" in call[: call.index(")")]


class TestEnforceSwitch:
    """``VLM_IMAGE_LIMITS_ENFORCE=false`` restores the fixed cap at upload."""

    def test_switch_off_uses_the_fixed_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VLM_IMAGE_ANSWER_PAGE_CAP", raising=False)
        monkeypatch.setenv("VLM_IMAGE_LIMITS_ENFORCE", "false")
        # Bedrock would reject 21 pages; the fixed cap (90) accepts them.
        check(_pdf(21), _PDF, _llm_profile(_BEDROCK_ID, _BEDROCK_META))
        with pytest.raises(ImageModePageLimitExceeded) as excinfo:
            check(_pdf(91), _PDF, _llm_profile(_BEDROCK_ID, _BEDROCK_META))
        assert "the limit is 90" in str(excinfo.value.detail)


def _cached_summary(pages: int) -> str:
    """The extract text a cached image-mode extraction carries."""
    return _psh_mod.LLMWhispererHelper.build_image_output_summary([None] * pages)


class TestCacheHitCheck:
    """A cached image-mode extraction is re-checked like an upload (P3)."""

    cached_check = staticmethod(PromptStudioHelper._check_cached_image_extraction)

    @pytest.fixture(autouse=True)
    def _no_env_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VLM_IMAGE_ANSWER_PAGE_CAP", raising=False)

    def test_model_aware_rejects_over_the_llm_budget(self) -> None:
        with pytest.raises(_psh_mod.ExtractionAPIError) as excinfo:
            self.cached_check(
                _llm_profile(_BEDROCK_ID, _BEDROCK_META), _cached_summary(21), "a.pdf"
            )
        assert "20 page images" in str(excinfo.value.detail)

    def test_switch_off_applies_the_fixed_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_LIMITS_ENFORCE", "false")
        profile = _llm_profile(_BEDROCK_ID, _BEDROCK_META)
        # Over Bedrock's 20, inside the fixed cap (90): accepted.
        self.cached_check(profile, _cached_summary(21), "a.pdf")
        with pytest.raises(_psh_mod.ExtractionAPIError) as excinfo:
            self.cached_check(profile, _cached_summary(91), "a.pdf")
        detail = str(excinfo.value.detail)
        assert "IMAGE_PAGE_CAP_EXCEEDED" in detail
        assert "the limit is 90" in detail

    def test_switch_off_honours_the_page_cap_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_LIMITS_ENFORCE", "false")
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "5")
        with pytest.raises(_psh_mod.ExtractionAPIError):
            self.cached_check(
                _llm_profile(_BEDROCK_ID, _BEDROCK_META), _cached_summary(6), "a.pdf"
            )
