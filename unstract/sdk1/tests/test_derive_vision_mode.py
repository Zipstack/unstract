"""Tests for derive_vision_mode() and vision constants."""

from typing import Self

from unstract.sdk1.constants import (
    ExtractionInputs,
    SourceOfTruthValues,
    VisionMode,
    derive_vision_mode,
)


class TestVisionModeConstants:
    """Verify vision mode string constants are correct."""

    def test_vision_mode_values(self: Self) -> None:
        """VisionMode should expose the expected string values."""
        assert VisionMode.TEXT_ONLY == "text_only"
        assert VisionMode.SPATIAL_HELPER == "spatial_helper"
        assert VisionMode.SOURCE_OF_TRUTH == "source_of_truth"

    def test_extraction_inputs_values(self: Self) -> None:
        """ExtractionInputs should expose the expected string values."""
        assert ExtractionInputs.TEXT == "text"
        assert ExtractionInputs.IMAGE == "image"
        assert ExtractionInputs.BOTH == "both"

    def test_source_of_truth_values(self: Self) -> None:
        """SourceOfTruthValues should expose the expected string values."""
        assert SourceOfTruthValues.TEXT == "text"
        assert SourceOfTruthValues.IMAGE == "image"


class TestDeriveVisionMode:
    """Tests for derive_vision_mode() derivation logic.

    Derivation table:
        | extraction_inputs | source_of_truth | vision_mode       |
        |-------------------|-----------------|-------------------|
        | text              | (ignored)       | text_only         |
        | image             | (ignored)       | source_of_truth   |
        | both              | text            | spatial_helper    |
        | both              | image           | source_of_truth   |
    """

    def test_text_returns_text_only(self: Self) -> None:
        """extraction_inputs=text -> text_only, source_of_truth ignored."""
        assert derive_vision_mode("text", "text") == VisionMode.TEXT_ONLY
        assert derive_vision_mode("text", "image") == VisionMode.TEXT_ONLY

    def test_image_returns_source_of_truth(self: Self) -> None:
        """extraction_inputs=image -> source_of_truth, always."""
        assert derive_vision_mode("image", "text") == VisionMode.SOURCE_OF_TRUTH
        assert derive_vision_mode("image", "image") == VisionMode.SOURCE_OF_TRUTH

    def test_both_text_sot_returns_spatial_helper(self: Self) -> None:
        """extraction_inputs=both, source_of_truth=text -> spatial_helper."""
        assert derive_vision_mode("both", "text") == VisionMode.SPATIAL_HELPER

    def test_both_image_sot_returns_source_of_truth(self: Self) -> None:
        """extraction_inputs=both, source_of_truth=image -> source_of_truth."""
        assert derive_vision_mode("both", "image") == VisionMode.SOURCE_OF_TRUTH

    def test_with_enum_constants(self: Self) -> None:
        """Verify the function works with class constants."""
        assert (
            derive_vision_mode(ExtractionInputs.TEXT, SourceOfTruthValues.TEXT)
            == VisionMode.TEXT_ONLY
        )
        assert (
            derive_vision_mode(ExtractionInputs.IMAGE, SourceOfTruthValues.TEXT)
            == VisionMode.SOURCE_OF_TRUTH
        )
        assert (
            derive_vision_mode(ExtractionInputs.BOTH, SourceOfTruthValues.TEXT)
            == VisionMode.SPATIAL_HELPER
        )
        assert (
            derive_vision_mode(ExtractionInputs.BOTH, SourceOfTruthValues.IMAGE)
            == VisionMode.SOURCE_OF_TRUTH
        )
