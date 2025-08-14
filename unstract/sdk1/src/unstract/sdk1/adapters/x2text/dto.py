from dataclasses import dataclass


@dataclass
class TextExtractionMetadata:
    whisper_hash: str


@dataclass
class TextExtractionResult:
    extracted_text: str
    extraction_metadata: TextExtractionMetadata | None = None
