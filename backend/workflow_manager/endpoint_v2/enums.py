from enum import Enum


class FileProcessingStatus(Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class AllowedFileTypes(Enum):
    """MIME types accepted into a workflow.

    Mirrors LLMWhisperer's own gate, `Util.is_valid_file_type_from_path`
    (unstract-llm-whisperer `backend/app/util/base.py`), member for member.
    Accepting what it cannot read only defers the failure to extraction, and
    rejecting what it can read loses a file that would have worked - so the two
    sets have to move together. Keep in step with
    workers/shared/enums/file_types.py.
    """

    PLAIN_TEXT = "text/plain"
    PDF = "application/pdf"
    JPEG = "image/jpeg"
    PNG = "image/png"
    TIFF = "image/tiff"
    BMP = "image/bmp"
    GIF = "image/gif"
    WEBP = "image/webp"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    DOC = "application/msword"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    XLS = "application/vnd.ms-excel"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    PPT = "application/vnd.ms-powerpoint"
    ODT = "application/vnd.oasis.opendocument.text"
    ODS = "application/vnd.oasis.opendocument.spreadsheet"
    ODP = "application/vnd.oasis.opendocument.presentation"
    CDFV2 = "application/CDFV2"
    JSON = "application/json"
    CSV = "text/csv"

    @classmethod
    def is_allowed(cls, mime_type: str) -> bool:
        """Whether LLMWhisperer would accept this type.

        Any `text/*` passes, which is how html, xml, tsv, rtf and markdown are
        handled - they reach the extractor as text rather than as a listed
        format. The enum covers everything else.
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
    """
    if mime_type not in INCONCLUSIVE_MIME_TYPES:
        return mime_type
    if b"%PDF-" in head[:PDF_HEADER_SCAN_BYTES]:
        return AllowedFileTypes.PDF.value
    return mime_type
