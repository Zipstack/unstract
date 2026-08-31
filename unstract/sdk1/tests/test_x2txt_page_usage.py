"""Tests for page usage accounting in X2Text.

Regression cover for UN-4042: page usage was counted from the input file, so a
199-page PDF with ``pages_to_extract = "1-5"`` was billed 199 pages while
LLMWhisperer billed the 5 it actually extracted.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import LLMWhispererHelper
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.llm_whisperer_v2 import (
    LLMWhispererV2,
)
from unstract.sdk1.constants import MimeType
from unstract.sdk1.x2txt import X2Text


@pytest.fixture
def x2text() -> X2Text:
    """An X2Text with no adapter wired up — page usage needs neither."""
    tool = MagicMock()
    tool.get_env_or_die.return_value = "test-platform-api-key"
    return X2Text(tool=tool, usage_kwargs={"run_id": "test-run"})


@pytest.fixture
def pdf_fs() -> MagicMock:
    """A FileStorage standing in for a 199-page PDF."""
    fs = MagicMock()
    fs.read.return_value = b"%PDF-1.4 fake"
    return fs


def _pushed_page_count(audit: MagicMock) -> int:
    """The page_count handed to the platform by a single push."""
    audit.return_value.push_page_usage_data.assert_called_once()
    return audit.return_value.push_page_usage_data.call_args.kwargs["page_count"]


class TestPushUsageDetails:
    """What X2Text.push_usage_details reports to the audit service."""

    @patch("unstract.sdk1.x2txt.Audit")
    @patch("unstract.sdk1.x2txt.pdfplumber")
    @patch("unstract.sdk1.x2txt.ToolUtils.get_file_size", return_value=1234)
    def test_pdf_uses_extractor_page_count(
        self,
        _size: MagicMock,
        pdfplumber: MagicMock,
        audit: MagicMock,
        x2text: X2Text,
        pdf_fs: MagicMock,
    ) -> None:
        """UN-4042: 5 pages extracted from a 199-page PDF bills 5, not 199."""
        pdfplumber.open.return_value.__enter__.return_value.pages = [None] * 199

        x2text.push_usage_details("in.pdf", MimeType.PDF, fs=pdf_fs, page_count=5)

        assert _pushed_page_count(audit) == 5

    @patch("unstract.sdk1.x2txt.Audit")
    @patch("unstract.sdk1.x2txt.pdfplumber")
    @patch("unstract.sdk1.x2txt.ToolUtils.get_file_size", return_value=1234)
    def test_pdf_without_extractor_count_falls_back_to_file(
        self,
        _size: MagicMock,
        pdfplumber: MagicMock,
        audit: MagicMock,
        x2text: X2Text,
        pdf_fs: MagicMock,
    ) -> None:
        """Adapters that report nothing keep the pre-UN-4042 behaviour."""
        pdfplumber.open.return_value.__enter__.return_value.pages = [None] * 199

        x2text.push_usage_details("in.pdf", MimeType.PDF, fs=pdf_fs, page_count=None)

        assert _pushed_page_count(audit) == 199

    @pytest.mark.parametrize("bad_count", [0, -3])
    @patch("unstract.sdk1.x2txt.Audit")
    @patch("unstract.sdk1.x2txt.pdfplumber")
    @patch("unstract.sdk1.x2txt.ToolUtils.get_file_size", return_value=1234)
    def test_pdf_rejects_non_positive_count(
        self,
        _size: MagicMock,
        pdfplumber: MagicMock,
        audit: MagicMock,
        bad_count: int,
        x2text: X2Text,
        pdf_fs: MagicMock,
    ) -> None:
        """A zero or negative count must never bill zero pages."""
        pdfplumber.open.return_value.__enter__.return_value.pages = [None] * 199

        x2text.push_usage_details("in.pdf", MimeType.PDF, fs=pdf_fs, page_count=bad_count)

        assert _pushed_page_count(audit) == 199

    @patch("unstract.sdk1.x2txt.Audit")
    @patch("unstract.sdk1.x2txt.ToolUtils.get_file_size", return_value=99)
    def test_non_pdf_ignores_extractor_count(
        self,
        _size: MagicMock,
        audit: MagicMock,
        x2text: X2Text,
    ) -> None:
        """Non-PDF counting is UN-4043; this fix must not raise those bills."""
        x2text.push_usage_details("in.txt", MimeType.TEXT, fs=MagicMock(), page_count=20)

        assert _pushed_page_count(audit) == 1


class TestGetProcessedPageCount:
    """Reading processed_page_count out of an LLMWhisperer V2 response."""

    @pytest.mark.parametrize(
        "response,expected",
        [
            ({"whisper_metadata": {"processed_page_count": 5}}, 5),
            ({"whisper_metadata": {"processed_page_count": 1}}, 1),
            ({}, None),
            ({"whisper_metadata": None}, None),
            ({"whisper_metadata": "nope"}, None),
            ({"whisper_metadata": {}}, None),
            ({"whisper_metadata": {"processed_page_count": 0}}, None),
            ({"whisper_metadata": {"processed_page_count": -1}}, None),
            ({"whisper_metadata": {"processed_page_count": "5"}}, None),
            ({"whisper_metadata": {"processed_page_count": 5.0}}, None),
            # isinstance(True, int) is True — must not bill 1 page for a bool.
            ({"whisper_metadata": {"processed_page_count": True}}, None),
        ],
    )
    def test_validates_response(
        self, response: dict[str, Any], expected: int | None
    ) -> None:
        assert LLMWhispererHelper.get_processed_page_count(response) == expected


class TestProcessForwardsPageCount:
    """The wiring: what the adapter reports is what gets billed."""

    @patch("unstract.sdk1.x2txt.Audit")
    @patch("unstract.sdk1.x2txt.pdfplumber")
    @patch("unstract.sdk1.x2txt.ToolUtils.get_file_size", return_value=1234)
    def test_process_bills_the_count_the_adapter_reported(
        self,
        _size: MagicMock,
        pdfplumber: MagicMock,
        audit: MagicMock,
        x2text: X2Text,
        pdf_fs: MagicMock,
    ) -> None:
        """A 199-page PDF extracted with a 5-page range is billed 5."""
        pdfplumber.open.return_value.__enter__.return_value.pages = [None] * 199
        pdf_fs.mime_type.return_value = MimeType.PDF
        x2text._x2text_instance = MagicMock()
        x2text._x2text_instance.process.return_value = TextExtractionResult(
            extracted_text="five pages of text", page_count=5
        )

        result = x2text.process("in.pdf", fs=pdf_fs)

        assert _pushed_page_count(audit) == 5
        assert result.page_count == 5

    @patch("unstract.sdk1.x2txt.Audit")
    @patch("unstract.sdk1.x2txt.pdfplumber")
    @patch("unstract.sdk1.x2txt.ToolUtils.get_file_size", return_value=1234)
    def test_process_falls_back_for_adapters_reporting_nothing(
        self,
        _size: MagicMock,
        pdfplumber: MagicMock,
        audit: MagicMock,
        x2text: X2Text,
        pdf_fs: MagicMock,
    ) -> None:
        """LlamaParse, Unstructured and NoOp report no count — behaviour is unchanged."""
        pdfplumber.open.return_value.__enter__.return_value.pages = [None] * 199
        pdf_fs.mime_type.return_value = MimeType.PDF
        x2text._x2text_instance = MagicMock()
        x2text._x2text_instance.process.return_value = TextExtractionResult(
            extracted_text="all of it"
        )

        x2text.process("in.pdf", fs=pdf_fs)

        assert _pushed_page_count(audit) == 199


class TestLLMWhispererV2ReportsPageCount:
    """The V2 adapter lifts processed_page_count off the whisper response."""

    @patch.object(LLMWhispererHelper, "extract_text_from_response", return_value="text")
    @patch.object(LLMWhispererHelper, "send_whisper_request")
    def test_page_count_taken_from_whisper_metadata(
        self, send: MagicMock, _extract: MagicMock
    ) -> None:
        send.return_value = {
            "whisper_hash_v2": "hash-1",
            "result_text": "text",
            "whisper_metadata": {
                "processed_page_count": 5,
                "requested_page_count": 5,
                "total_page_count": 199,
            },
        }

        result = LLMWhispererV2({}).process("in.pdf", fs=MagicMock())

        assert result.page_count == 5

    @patch.object(LLMWhispererHelper, "extract_text_from_response", return_value="text")
    @patch.object(LLMWhispererHelper, "send_whisper_request")
    def test_page_count_is_none_when_metadata_absent(
        self, send: MagicMock, _extract: MagicMock
    ) -> None:
        """Older LLMWhisperer deployments omit whisper_metadata entirely."""
        send.return_value = {"whisper_hash_v2": "hash-1", "result_text": "text"}

        result = LLMWhispererV2({}).process("in.pdf", fs=MagicMock())

        assert result.page_count is None
