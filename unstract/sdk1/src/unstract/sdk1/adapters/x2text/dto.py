from dataclasses import dataclass
from typing import Any


@dataclass
class TextExtractionMetadata:
    whisper_hash: str
    line_metadata: dict[Any, Any] | None = None


@dataclass
class TextExtractionResult:
    extracted_text: str
    extraction_metadata: TextExtractionMetadata | None = None
