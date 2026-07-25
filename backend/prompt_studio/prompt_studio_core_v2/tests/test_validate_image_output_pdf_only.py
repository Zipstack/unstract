"""Unit tests for ``PromptStudioHelper._validate_image_output_pdf_only``.

Pins the UNS-757 fail-fast guard: when the x2text adapter is in image
output mode, a non-PDF input must be rejected at index-build time with the
SDK's shared PDF-only message, so the user never has to wait for the
executor to fail the extraction. Every other combination must pass through.

Unit tests: the real helper module is imported (Django is loaded by the
rig's test env) and the profile is a lightweight mock, so no database is
touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod
from prompt_studio.prompt_studio_core_v2.exceptions import IndexingAPIError
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.constants import (
    ImageOutputConfig,
)

PromptStudioHelper = _psh_mod.PromptStudioHelper


def _profile(metadata: dict | None) -> MagicMock:
    """A profile whose x2text adapter exposes ``metadata`` verbatim."""
    profile = MagicMock(name="ProfileManager")
    profile.x2text.metadata = metadata
    return profile


class TestImageModeRejectsNonPdf:
    """Image output mode + non-PDF → IndexingAPIError(400, PDF-only)."""

    @pytest.mark.parametrize("file_name", ["statement.docx", "notes.txt", "a.png"])
    def test_non_pdf_raises(self, file_name: str) -> None:
        with pytest.raises(IndexingAPIError) as exc_info:
            PromptStudioHelper._validate_image_output_pdf_only(
                _profile({"output_mode": "image"}), file_name
            )
        assert exc_info.value.status_code == 400
        assert str(exc_info.value.detail) == ImageOutputConfig.PDF_ONLY_ERROR

    @pytest.mark.parametrize("file_name", ["statement.pdf", "STATEMENT.PDF"])
    def test_pdf_passes_case_insensitively(self, file_name: str) -> None:
        # Must not raise for PDF inputs regardless of extension casing.
        PromptStudioHelper._validate_image_output_pdf_only(
            _profile({"output_mode": "image"}), file_name
        )


class TestNonImageModesUnaffected:
    """Only image mode is gated; every other config is a no-op."""

    @pytest.mark.parametrize(
        "metadata",
        [
            {"output_mode": "text"},
            {"output_mode": "layout_preserving"},
            {},  # e.g. a non-LLMWhisperer adapter with no output_mode
            None,  # adapter metadata absent entirely
        ],
    )
    def test_non_image_mode_passes_for_non_pdf(self, metadata: dict | None) -> None:
        PromptStudioHelper._validate_image_output_pdf_only(
            _profile(metadata), "statement.docx"
        )

    def test_missing_x2text_adapter_passes(self) -> None:
        profile = MagicMock(name="ProfileManager")
        profile.x2text = None
        PromptStudioHelper._validate_image_output_pdf_only(profile, "statement.docx")
