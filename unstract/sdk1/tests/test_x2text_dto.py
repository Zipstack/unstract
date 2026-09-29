"""Unit tests for x2text DTOs — image output mode extension (MUNS-193).

Covers:
- UNS-730: PageImageReference dataclass shape.
- UNS-731: additive, non-breaking ``page_images`` field on
  TextExtractionMetadata.
- UNS-734: non-breaking serialization + round-trip guarantees.
- UNS-735: PageImageReference.to_dict / from_dict helpers.

All tests are pure in-memory unit tests: no live services, file storage, or
network calls.
"""

from dataclasses import asdict

from unstract.sdk1.adapters.x2text.dto import (
    PageImageReference,
    TextExtractionMetadata,
    TextExtractionResult,
)
from unstract.sdk1.file_storage import FileStorageProvider


def _serialize(obj: object) -> dict:
    """Serialize a dataclass, omitting None-valued fields.

    Mirrors a None-omitting wire convention: optional fields left unset never
    introduce new keys, which is precisely the non-breaking guarantee under
    test for existing (text-mode) consumers.
    """
    return {k: v for k, v in asdict(obj).items() if v is not None}


class TestNonBreakingSerialization:
    """The additive ``page_images`` field must not change text-mode output."""

    def test_text_mode_metadata_matches_baseline(self) -> None:
        # Baseline = the exact key set produced before page_images existed.
        baseline = {"whisper_hash": "abc123"}
        meta = TextExtractionMetadata(whisper_hash="abc123")

        assert meta.page_images is None
        assert _serialize(meta) == baseline
        assert "page_images" not in _serialize(meta)

    def test_text_mode_metadata_full_fields_unchanged(self) -> None:
        meta = TextExtractionMetadata(
            whisper_hash="h",
            line_metadata={"1": "x"},
        )
        assert _serialize(meta) == {
            "whisper_hash": "h",
            "line_metadata": {"1": "x"},
        }

    def test_result_default_serialization_unchanged(self) -> None:
        result = TextExtractionResult(extracted_text="hello")
        assert _serialize(result) == {"extracted_text": "hello"}


class TestImageModeRoundTrip:
    """Metadata carrying page_images must round-trip losslessly."""

    def test_metadata_with_page_images_round_trips(self) -> None:
        original = TextExtractionMetadata(
            whisper_hash="h",
            page_images=[
                PageImageReference(page_number=1, path="doc/page_001.png"),
                PageImageReference(
                    page_number=2,
                    path="doc/page_002.png",
                    filename="page_002.png",
                    size_bytes=2048,
                    provider=FileStorageProvider.S3,
                ),
            ],
        )
        # Serialize to a wire form using the per-page to_dict helper...
        wire = {
            "whisper_hash": original.whisper_hash,
            "page_images": [pi.to_dict() for pi in original.page_images],
        }
        # ...then deserialize back into an equivalent object.
        restored = TextExtractionMetadata(
            whisper_hash=wire["whisper_hash"],
            page_images=[PageImageReference.from_dict(d) for d in wire["page_images"]],
        )
        assert restored == original

    def test_metadata_page_images_none_round_trips(self) -> None:
        original = TextExtractionMetadata(whisper_hash="h")
        restored = TextExtractionMetadata(**asdict(original))
        assert restored == original
        assert restored.page_images is None


class TestPageImageReferenceSerialization:
    """to_dict/from_dict coverage for minimal and full field sets."""

    def test_construct_with_required_fields_only(self) -> None:
        ref = PageImageReference(page_number=5, path="p")
        assert ref.page_number == 5
        assert ref.path == "p"
        assert ref.filename is None
        assert ref.size_bytes is None
        assert ref.provider is None

    def test_minimal_round_trip(self) -> None:
        ref = PageImageReference(page_number=1, path="doc/page_001.png")
        restored = PageImageReference.from_dict(ref.to_dict())
        assert restored == ref

    def test_full_round_trip_serializes_provider_to_value(self) -> None:
        ref = PageImageReference(
            page_number=3,
            path="doc/page_003.png",
            filename="page_003.png",
            size_bytes=4096,
            provider=FileStorageProvider.LOCAL,
        )
        as_dict = ref.to_dict()
        # Enum is serialized to its string value for JSON-friendliness.
        assert as_dict["provider"] == "local"

        restored = PageImageReference.from_dict(as_dict)
        assert restored == ref
        assert restored.provider is FileStorageProvider.LOCAL
