from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unstract.sdk1.file_storage import FileStorageProvider


@dataclass
class TextExtractionMetadata:
    whisper_hash: str
    line_metadata: dict[Any, Any] | None = None
    # Optional, additive field populated only in image output mode. Defaults to
    # None so existing text-mode consumers are entirely unaffected (the field is
    # never encoded into ``extracted_text``). See PageImageReference below.
    page_images: list[PageImageReference] | None = None


@dataclass
class TextExtractionResult:
    extracted_text: str
    extraction_metadata: TextExtractionMetadata | None = None


@dataclass
class PageImageReference:
    """Per-page image reference for image-mode extraction results.

    Produced by the LLMWhisperer image output mode: each entry points to a
    single page image that has been persisted to Unstract's FileStorage. This
    is a dedicated value object so image references are never smuggled inside
    the string ``extracted_text`` field used by text-mode consumers.

    Attributes:
        page_number: 1-based index of the page this image represents.
        path: FileStorage path / reference string to the stored page image.
        filename: Stored image filename (e.g. ``page_001.png``). Optional.
        size_bytes: Size of the stored image file in bytes. Optional.
        provider: FileStorageProvider backend (LOCAL/S3/...) holding the
            image. Optional.
    """

    page_number: int
    path: str
    filename: str | None = None
    size_bytes: int | None = None
    provider: FileStorageProvider | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain, JSON-friendly dictionary.

        The ``provider`` enum is stored as its string value so the result is
        directly serializable; ``from_dict`` reverses this.
        """
        return {
            "page_number": self.page_number,
            "path": self.path,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "provider": self.provider.value if self.provider is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageImageReference:
        """Reconstruct a PageImageReference from ``to_dict`` output.

        Round-trips with ``to_dict``: ``from_dict(ref.to_dict()) == ref``.
        """
        provider = data.get("provider")
        return cls(
            page_number=data["page_number"],
            path=data["path"],
            filename=data.get("filename"),
            size_bytes=data.get("size_bytes"),
            provider=FileStorageProvider(provider) if provider is not None else None,
        )
