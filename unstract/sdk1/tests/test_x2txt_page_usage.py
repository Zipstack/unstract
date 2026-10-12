"""Tests for page usage accounting in X2Text.

PDF page usage follows the extractor's processed page count, so a page range
is billed for the pages extracted, not the whole file.
"""

from collections.abc import Iterator
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

PDF_PAGES = 199


@pytest.fixture
def x2text() -> X2Text:
    """An X2Text with no adapter configured; page usage does not need one."""
    tool = MagicMock()
    tool.get_env_or_die.return_value = "test-platform-api-key"
    return X2Text(tool=tool, usage_kwargs={"run_id": "test-run"})


@pytest.fixture
def pdf_fs() -> MagicMock:
    """A FileStorage returning placeholder PDF bytes; `audit` patches pdfplumber."""
    fs = MagicMock()
    fs.read.return_value = b"%PDF-1.4 fake"
    fs.mime_type.return_value = MimeType.PDF
    return fs


@pytest.fixture
def audit() -> Iterator[MagicMock]:
    """The Audit mock, with any PDF counted by pdfplumber as PDF_PAGES pages."""
    with (
        patch("unstract.sdk1.x2txt.Audit") as audit,
        patch("unstract.sdk1.x2txt.pdfplumber") as pdfplumber,
        patch("unstract.sdk1.x2txt.ToolUtils.get_file_size", return_value=1234),
    ):
        pdfplumber.open.return_value.__enter__.return_value.pages = [None] * PDF_PAGES
        yield audit


def _pushed_page_count(audit: MagicMock) -> int:
    """The page_count handed to the platform by a single push."""
    audit.return_value.push_page_usage_data.assert_called_once()
    return audit.return_value.push_page_usage_data.call_args.kwargs["page_count"]


class TestPushUsageDetails:
    """What X2Text.push_usage_details reports to the audit service."""

    def test_pdf_uses_extractor_page_count(
        self, audit: MagicMock, x2text: X2Text, pdf_fs: MagicMock
    ) -> None:
        """5 pages extracted from a 199-page PDF bills 5, not 199."""
        x2text.push_usage_details("in.pdf", MimeType.PDF, fs=pdf_fs, page_count=5)

        assert _pushed_page_count(audit) == 5

    @pytest.mark.parametrize("bad_count", [None, 0, -3, True, 2.5])
    def test_pdf_rejects_unusable_count(
        self, audit: MagicMock, bad_count: object, x2text: X2Text, pdf_fs: MagicMock
    ) -> None:
        """A count that is not a positive int falls back to the PDF's pages."""
        x2text.push_usage_details("in.pdf", MimeType.PDF, fs=pdf_fs, page_count=bad_count)

        assert _pushed_page_count(audit) == PDF_PAGES

    def test_non_pdf_ignores_extractor_count(
        self, audit: MagicMock, x2text: X2Text
    ) -> None:
        """Non-PDF billing must not change with the reported count."""
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

    @pytest.mark.parametrize(
        "metadata", [{}, {"whisper_metadata": {"processed_page_count": 0}}]
    )
    def test_warns_when_count_unusable(
        self, metadata: dict[str, Any], caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unusable count must be visible, since billing then counts the file."""
        with caplog.at_level("WARNING"):
            LLMWhispererHelper.get_processed_page_count(
                {"whisper_hash": "wh-1", **metadata}
            )

        assert "wh-1" in caplog.text

    def test_silent_when_count_usable(self, caplog: pytest.LogCaptureFixture) -> None:
        response = {"whisper_metadata": {"processed_page_count": 5}}
        with caplog.at_level("WARNING"):
            LLMWhispererHelper.get_processed_page_count(response)

        assert caplog.text == ""


class TestProcessForwardsPageCount:
    """The wiring: what the adapter reports is what gets billed."""

    @pytest.mark.parametrize("reported,billed", [(5, 5), (None, PDF_PAGES)])
    def test_process_bills_the_count_the_adapter_reported(
        self,
        audit: MagicMock,
        reported: int | None,
        billed: int,
        x2text: X2Text,
        pdf_fs: MagicMock,
    ) -> None:
        """A reported count is billed; adapters reporting none fall back to the PDF."""
        x2text._x2text_instance = MagicMock()
        x2text._x2text_instance.process.return_value = TextExtractionResult(
            extracted_text="text", page_count=reported
        )

        x2text.process("in.pdf", fs=pdf_fs)

        assert _pushed_page_count(audit) == billed


class TestLLMWhispererV2ReportsPageCount:
    """The V2 adapter lifts processed_page_count off the whisper response."""

    @patch.object(LLMWhispererHelper, "extract_text_from_response", return_value="text")
    @patch.object(LLMWhispererHelper, "send_whisper_request")
    def test_page_count_taken_from_whisper_metadata(
        self, send: MagicMock, _extract: MagicMock
    ) -> None:
        send.return_value = {
            "whisper_hash": "hash-1",
            "whisper_metadata": {"processed_page_count": 5, "total_page_count": 199},
        }

        result = LLMWhispererV2({}).process("in.pdf", fs=MagicMock())

        assert result.page_count == 5
