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
from unittest.mock import MagicMock

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
