"""Unit tests for the image-output PDF-only guard.

Pins the fail-fast guard: when the x2text adapter is the LLMWhisperer adapter
in image output mode, a non-PDF input must be rejected (with the SDK's shared
PDF-only message) before extraction is dispatched. Every other combination —
non-image mode, a non-LLMWhisperer adapter, a PDF input — must pass through.
Also pins that the guard is actually wired into ``dynamic_extractor`` (the
single extract choke point), so it cannot become unreachable unnoticed.

Unit tests: the real helper module is imported (Django is loaded by the rig's
test env) and the profile is a lightweight mock, so no database is touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod
from prompt_studio.prompt_studio_core_v2.exceptions import IndexingAPIError
from unstract.sdk1.adapters.x2text.constants import ImageOutputConstants

PromptStudioHelper = _psh_mod.PromptStudioHelper

_LLMW_ADAPTER_ID = "llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93"


def _profile(metadata: dict | None, adapter_id: str = _LLMW_ADAPTER_ID) -> MagicMock:
    """A profile whose x2text adapter exposes ``adapter_id`` + ``metadata``."""
    profile = MagicMock(name="ProfileManager")
    profile.x2text.adapter_id = adapter_id
    profile.x2text.metadata = metadata
    return profile


class TestImageModeRejectsNonPdf:
    """LLMWhisperer + image output mode + non-PDF → IndexingAPIError(400)."""

    @pytest.mark.parametrize("file_name", ["statement.docx", "notes.txt", "a.png"])
    def test_non_pdf_raises(self, file_name: str) -> None:
        with pytest.raises(IndexingAPIError) as exc_info:
            PromptStudioHelper._validate_image_output_pdf_only(
                _profile({"output_mode": "image"}), file_name
            )
        assert exc_info.value.status_code == 400
        assert str(exc_info.value.detail) == ImageOutputConstants.PDF_ONLY_ERROR

    @pytest.mark.parametrize("file_name", ["statement.pdf", "STATEMENT.PDF"])
    def test_pdf_passes_case_insensitively(self, file_name: str) -> None:
        PromptStudioHelper._validate_image_output_pdf_only(
            _profile({"output_mode": "image"}), file_name
        )


class TestGateConditions:
    """The guard is gated on BOTH the adapter id and the output mode."""

    @pytest.mark.parametrize(
        "metadata",
        [{"output_mode": "text"}, {"output_mode": "layout_preserving"}, {}, None],
    )
    def test_non_image_mode_passes_for_non_pdf(self, metadata: dict | None) -> None:
        PromptStudioHelper._validate_image_output_pdf_only(
            _profile(metadata), "statement.docx"
        )

    def test_non_llmwhisperer_adapter_is_not_rejected(self) -> None:
        # A different x2text adapter that happens to carry output_mode=image in
        # its (user-editable) metadata must NOT inherit a PDF-only rejection.
        PromptStudioHelper._validate_image_output_pdf_only(
            _profile({"output_mode": "image"}, adapter_id="some-other|123"),
            "statement.docx",
        )

    def test_missing_x2text_adapter_passes(self) -> None:
        profile = MagicMock(name="ProfileManager")
        profile.x2text = None
        PromptStudioHelper._validate_image_output_pdf_only(profile, "statement.docx")


class TestGuardIsWiredIntoDynamicExtractor:
    """The guard must run from dynamic_extractor (the single extract path)."""

    def test_dynamic_extractor_rejects_non_pdf_image_mode(self) -> None:
        # The guard is the first statement in dynamic_extractor, so an image-mode
        # adapter + non-PDF raises before any DB/storage work — proving the call
        # site is exercised (deleting the call would make this test fail).
        profile = _profile({"output_mode": "image"})
        with pytest.raises(IndexingAPIError):
            PromptStudioHelper.dynamic_extractor(
                file_path="/data/statement.docx",
                enable_highlight=False,
                run_id="r1",
                org_id="org1",
                profile_manager=profile,
                document_id="doc1",
            )
