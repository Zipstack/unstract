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


class TestBrokenHooksBlockImageMode:
    """Half-broken cloud install (package present, hooks unimportable) →
    image-mode extraction is rejected outright, so a re-extraction can
    never rewrite pages while stale stored answers survive.
    """

    def test_broken_hooks_reject_image_mode_even_for_pdf(self, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.setattr(_psh_mod.vlm_utils, "VLM_HOOKS_BROKEN", True)
        with pytest.raises(IndexingAPIError) as exc_info:
            PromptStudioHelper._validate_image_output_pdf_only(
                _profile({"output_mode": "image"}), "statement.pdf"
            )
        assert exc_info.value.status_code == 500
        assert "failed to load" in str(exc_info.value.detail)

    def test_broken_hooks_do_not_affect_text_mode(self, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.setattr(_psh_mod.vlm_utils, "VLM_HOOKS_BROKEN", True)
        PromptStudioHelper._validate_image_output_pdf_only(
            _profile({"output_mode": "text"}), "statement.docx"
        )

    def test_healthy_state_passes_image_mode_pdf(self, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.setattr(_psh_mod.vlm_utils, "VLM_HOOKS_BROKEN", False)
        PromptStudioHelper._validate_image_output_pdf_only(
            _profile({"output_mode": "image"}), "statement.pdf"
        )


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


class TestInvalidationFailureClearsMarker:
    """A failing VLM invalidation hook must mark the hash failed.

    A success marker for the hash can pre-exist (the cache-hit path falls
    through to re-extraction when the text file is missing). If the hook
    raises and that marker survives, the retry cache-hits against the
    freshly written text file and never re-runs invalidation.
    """

    def test_hook_failure_marks_extraction_failed_and_reraises(
        self,
        monkeypatch,  # noqa: ANN001
    ) -> None:
        index_helper = MagicMock(name="PromptStudioIndexHelper")
        index_helper.check_extraction_status.return_value = False
        index_helper.mark_extraction_status.return_value = (
            _psh_mod.ExtractionStatusResult.OK
        )
        monkeypatch.setattr(_psh_mod, "PromptStudioIndexHelper", index_helper)
        monkeypatch.setattr(_psh_mod, "StateStore", MagicMock())
        monkeypatch.setattr(
            PromptStudioHelper, "_get_platform_api_key", MagicMock(return_value="k")
        )
        dispatcher = MagicMock()
        dispatcher.dispatch.return_value = MagicMock(
            success=True, data={"extracted_text": "new pages"}
        )
        monkeypatch.setattr(
            PromptStudioHelper, "_get_dispatcher", MagicMock(return_value=dispatcher)
        )
        monkeypatch.setattr(
            _psh_mod,
            "invalidate_vlm_answers_on_reextraction",
            MagicMock(side_effect=RuntimeError("boom")),
        )

        with pytest.raises(RuntimeError, match="boom"):
            PromptStudioHelper.dynamic_extractor(
                file_path="/data/statement.pdf",
                enable_highlight=False,
                run_id="r1",
                org_id="org1",
                profile_manager=_profile({"output_mode": "image"}),
                document_id="doc1",
            )

        index_helper.mark_extraction_status.assert_called_once()
        kwargs = index_helper.mark_extraction_status.call_args.kwargs
        assert kwargs["extracted"] is False
        assert "boom" in kwargs["error_message"]
