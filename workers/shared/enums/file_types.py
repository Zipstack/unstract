"""File type validation enums for worker processing.

This module defines allowed MIME types for file processing, matching the backend's
validation rules from workflow_manager/endpoint_v2/enums.py.
"""

from enum import Enum
from typing import Any

import magic


class AllowedFileTypes(Enum):
    """Allowed MIME types for file processing.

    This enum defines all supported file types that can be processed
    through the workflow system. It mirrors the backend's AllowedFileTypes
    to ensure consistency across the system.
    """

    # Text formats
    PLAIN_TEXT = "text/plain"
    CSV = "text/csv"
    JSON = "application/json"

    # Document formats
    PDF = "application/pdf"

    # Image formats
    JPEG = "image/jpeg"
    PNG = "image/png"
    TIFF = "image/tiff"
    BMP = "image/bmp"
    GIF = "image/gif"
    WEBP = "image/webp"

    # Microsoft Office formats
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    DOC = "application/msword"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    XLS = "application/vnd.ms-excel"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    PPT = "application/vnd.ms-powerpoint"

    # OpenDocument formats
    ODT = "application/vnd.oasis.opendocument.text"
    ODS = "application/vnd.oasis.opendocument.spreadsheet"
    ODP = "application/vnd.oasis.opendocument.presentation"

    # Other formats
    CDFV2 = "application/CDFV2"

    @classmethod
    def is_allowed(cls, mime_type: str) -> bool:
        """Check if a MIME type is allowed for processing.

        Any `text/*` passes, which is how html, xml, tsv, rtf and markdown reach
        the extractor as text rather than as a listed format.

        Args:
            mime_type: The MIME type string to validate

        Returns:
            bool: True if the MIME type is allowed, False otherwise
        """
        if mime_type.startswith("text/"):
            return True
        return mime_type in cls._value2member_map_


# libmagic yields these when it recognises a wrapper but not the content, so they
# are not a verdict on their own.
INCONCLUSIVE_MIME_TYPES = frozenset({"application/octet-stream", "application/zip"})

# libmagic's PDF rule only matches at offset 0, but extractors tolerate leading
# bytes before the header, so a stream-wrapped PDF sniffs as octet-stream. Eight
# bytes of padding is enough to trigger it. LLMWhisperer scans this same window
# for the same reason (Util.is_valid_file_type_from_path).
PDF_HEADER_SCAN_BYTES = 1024


def resolve_inconclusive_mime_type(mime_type: str, head: bytes) -> str:
    """Give a wrapper-only classification a second chance from the leading bytes.

    LLMWhisperer resolves these with Magika and then a `%PDF-` scan; without
    Magika this covers the PDF case, which is the one that reaches us.

    Deliberately stricter than that scan in two ways, because this promotes a
    file *into* the allow-list: a recognised zip is left alone however its
    entries happen to read, and the marker is re-classified from its own offset
    rather than trusted as a substring, so a stray "%PDF-" sitting inside other
    content cannot smuggle a file through the gate.
    """
    if mime_type not in INCONCLUSIVE_MIME_TYPES:
        return mime_type
    if mime_type == "application/zip":
        return mime_type
    offset = head[:PDF_HEADER_SCAN_BYTES].find(b"%PDF-")
    if offset == -1:
        return mime_type
    return magic.from_buffer(head[offset:], mime=True)


class FileProcessingOrder(str, Enum):
    """File processing order for SourceKey.FILE_PROCESSING_ORDER.

    This enum matches exactly with backend/workflow_manager/endpoint_v2/constants.py:FileProcessingOrder
    to ensure consistent ordering behavior across backend and workers.

    Semantics:
    - oldest_first: ascending last-modified time (mtime) - FIFO
    - newest_first: descending mtime - LIFO
    - unordered: no explicit ordering (OS enumeration order; may be nondeterministic)
    """

    UNORDERED = "unordered"
    OLDEST_FIRST = "oldest_first"  # FIFO
    NEWEST_FIRST = "newest_first"  # LIFO

    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values as a list."""
        return [v.value for v in cls]

    @classmethod
    def from_value(
        cls, value: Any, default: "FileProcessingOrder" = None
    ) -> "FileProcessingOrder":
        """Convert a value to FileProcessingOrder enum, with fallback to default.

        Args:
            value: The value to convert (can be string, enum, or None)
            default: Default value if conversion fails (defaults to UNORDERED)

        Returns:
            FileProcessingOrder enum value
        """
        if default is None:
            default = cls.UNORDERED

        if not value:
            return default

        # Handle string values
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                return default

        # Handle enum values
        if isinstance(value, cls):
            return value

        # Handle other types by converting to string
        try:
            return cls(str(value))
        except (ValueError, TypeError):
            return default
