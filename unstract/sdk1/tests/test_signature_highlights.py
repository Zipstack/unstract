"""Tests for LLMWhisperer document_insights signature helpers.

Focus: the page-key conversions. Page keys arrive verbatim from the
LLMWhisperer response, so a non-numeric key must degrade gracefully
instead of aborting prompt construction or text extraction.
"""

from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.llm_whisperer_v2 import (
    LLMWhispererV2,
)
from unstract.sdk1.utils.signature_highlights import format_signature_metadata_context


class TestFormatSignatureMetadataContext:
    """Tests for the LLM context block built from signature metadata."""

    def test_pages_sorted_numerically_and_displayed_one_indexed(self) -> None:
        context = format_signature_metadata_context(
            {
                "10": [{"name": "Late Signer", "type": "signature", "desc": ""}],
                "2": [{"name": "Early Signer", "type": "signature", "desc": "CFO"}],
            }
        )

        assert "- Page 3: Early Signer (signature) — CFO" in context
        assert "- Page 11: Late Signer (signature)" in context
        assert context.index("Early Signer") < context.index("Late Signer")

    def test_non_numeric_page_key_kept_verbatim_and_sorted_last(self) -> None:
        context = format_signature_metadata_context(
            {
                "cover": [{"name": "Odd Signer", "type": "signature", "desc": ""}],
                "0": [{"name": "First Signer", "type": "signature", "desc": ""}],
            }
        )

        assert "- Page 1: First Signer (signature)" in context
        assert "- Page cover: Odd Signer (signature)" in context
        assert context.index("First Signer") < context.index("Odd Signer")

    def test_non_dict_signature_entry_skipped(self) -> None:
        context = format_signature_metadata_context(
            {"0": ["not-a-dict", {"name": "Real Signer", "type": "signature"}]}
        )

        assert "- Page 1: Real Signer (signature)" in context

    def test_no_signatures_returns_empty_string(self) -> None:
        assert format_signature_metadata_context({"0": [], "1": []}) == ""


class TestBuildSignaturePageReferences:
    """Tests for the adapter helper that resolves signature page coords."""

    LINE_METADATA = [
        [0, 0, 0, 3168],  # marker row — zero height, skipped
        [0, 320, 31, 3168],
        [1, 100, 40, 3168],
    ]

    def test_non_numeric_page_key_skipped(self) -> None:
        references = LLMWhispererV2._build_signature_page_references(
            {
                "cover": [{"name": "Odd Signer"}],
                "1": [{"name": "Real Signer"}],
            },
            self.LINE_METADATA,
        )

        assert references == {
            "1": {
                "hex": "0x03",
                "line_metadata_index": 2,
                "signers": ["Real Signer"],
                "coords": [1, 100, 40, 3168],
            }
        }

    def test_only_non_numeric_keys_returns_none(self) -> None:
        assert (
            LLMWhispererV2._build_signature_page_references(
                {"cover": [{"name": "Odd Signer"}]}, self.LINE_METADATA
            )
            is None
        )

    def test_first_content_line_used_skipping_marker_rows(self) -> None:
        references = LLMWhispererV2._build_signature_page_references(
            {"0": [{"name": "Signer"}]}, self.LINE_METADATA
        )

        assert references["0"]["line_metadata_index"] == 1
        assert references["0"]["coords"] == [0, 320, 31, 3168]
