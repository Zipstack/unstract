from dataclasses import dataclass
from typing import Any


@dataclass
class TextExtractionMetadata:
    whisper_hash: str
    line_metadata: dict[Any, Any] | None = None


@dataclass
class TextExtractionResult:
    """Outcome of a text extraction.

    Attributes:
        extracted_text: The text the extractor produced.
        extraction_metadata: Extractor-specific metadata, if any.
        page_count: Pages the extractor actually processed. Set by adapters that
            report it, so that a document extracted with a page range is billed
            for the pages read rather than every page in the file (UN-4042).
            None when the adapter reports no count.
    """

    extracted_text: str
    extraction_metadata: TextExtractionMetadata | None = None
    page_count: int | None = None
