"""Tests for LLMWhispererV2.process() output-mode branching (MUNS-195).

Covers image/text branching (UNS-749), PDF-only validation (UNS-749/757),
image-mode result population (UNS-751), and the text-mode regression guarantee
that image logic is never triggered in text mode (UNS-753).

Network and the image helper flow are stubbed — no live service is contacted.
"""

import pytest
from _pytest.monkeypatch import MonkeyPatch

from unstract.sdk1.adapters.exceptions import ExtractorError
from unstract.sdk1.adapters.x2text.dto import PageImageReference
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
    LLMWhispererHelper,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.llm_whisperer_v2 import (
    LLMWhispererV2,
)

_BASE_CONFIG = {"url": "https://svc.example.com", "unstract_key": "key"}


def _adapter(**overrides: object) -> LLMWhispererV2:
    return LLMWhispererV2({**_BASE_CONFIG, **overrides})


class TestTextModeRegression:
    def test_text_mode_follows_existing_path(self, monkeypatch: MonkeyPatch) -> None:
        image_called = {"hit": False}
        monkeypatch.setattr(
            LLMWhispererHelper,
            "send_whisper_request",
            lambda **_: {"whisper_hash": "wh1", "line_metadata": [[1, 0, 10, 100]]},
        )
        monkeypatch.setattr(
            LLMWhispererHelper,
            "extract_text_from_response",
            lambda *_a, **_k: "hello text",
        )
        monkeypatch.setattr(
            LLMWhispererHelper,
            "get_page_images",
            lambda **_: image_called.__setitem__("hit", True),
        )

        result = _adapter().process("in.pdf")

        assert result.extracted_text == "hello text"
        assert result.extraction_metadata.whisper_hash == "wh1"
        assert result.extraction_metadata.page_images is None
        assert image_called["hit"] is False  # image path never touched

    def test_text_mode_error_path_propagates(self, monkeypatch: MonkeyPatch) -> None:
        def _boom(**_: object) -> None:
            raise ExtractorError("service error", status_code=500)

        monkeypatch.setattr(LLMWhispererHelper, "send_whisper_request", _boom)
        adapter = _adapter()
        with pytest.raises(ExtractorError, match="service error"):
            adapter.process("in.pdf")


class TestImageModeBranch:
    def test_populates_page_images_and_empty_text(self, monkeypatch: MonkeyPatch) -> None:
        refs = [
            PageImageReference(page_number=1, path="d/pages/page_001.png"),
            PageImageReference(page_number=2, path="d/pages/page_002.png"),
        ]
        captured: dict[str, object] = {}

        def _fake_get_page_images(**kwargs: object) -> list[PageImageReference]:
            captured.update(kwargs)
            return refs

        monkeypatch.setattr(LLMWhispererHelper, "get_page_images", _fake_get_page_images)
        monkeypatch.setattr(
            LLMWhispererHelper,
            "send_whisper_request",
            lambda **_: pytest.fail("text path must not run in image mode"),
        )

        result = _adapter(output_mode="image").process("in.pdf", "out.txt")

        assert result.extracted_text == ""  # plain string, never JSON
        assert result.extraction_metadata.page_images == refs
        assert captured["input_file_path"] == "in.pdf"
        assert captured["output_file_path"] == "out.txt"

    def test_empty_page_list_is_safe(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(LLMWhispererHelper, "get_page_images", lambda **_: [])
        result = _adapter(output_mode="image").process("in.pdf")
        assert result.extraction_metadata.page_images == []
        assert result.extracted_text == ""

    def test_tag_forwarded_to_helper(self, monkeypatch: MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        def _capture(**kwargs: object) -> list:
            captured.update(kwargs)
            return []

        monkeypatch.setattr(LLMWhispererHelper, "get_page_images", _capture)
        _adapter(output_mode="image").process("in.pdf", tags=["cust-42"])
        assert captured["tag"] == ["cust-42"]

    def test_pdf_extension_is_case_insensitive(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(LLMWhispererHelper, "get_page_images", lambda **_: [])
        # Should not raise for an uppercase .PDF extension.
        _adapter(output_mode="image").process("SCAN.PDF")


class TestPdfOnlyValidation:
    def test_non_pdf_rejected_before_helper_runs(self, monkeypatch: MonkeyPatch) -> None:
        image_called = {"hit": False}
        monkeypatch.setattr(
            LLMWhispererHelper,
            "get_page_images",
            lambda **_: image_called.__setitem__("hit", True) or [],
        )
        adapter = _adapter(output_mode="image")
        with pytest.raises(ExtractorError, match="PDF input only"):
            adapter.process("in.png")
        assert image_called["hit"] is False

    def test_validate_pdf_only_accepts_pdf(self) -> None:
        LLMWhispererV2._validate_pdf_only("/tmp/doc.pdf")  # no raise

    def test_validate_pdf_only_rejects_other(self) -> None:
        with pytest.raises(ExtractorError, match="PDF input only"):
            LLMWhispererV2._validate_pdf_only("/tmp/doc.tiff")
