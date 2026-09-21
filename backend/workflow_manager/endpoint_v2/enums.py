from enum import Enum

from unstract.core.mime_gate import (  # noqa: F401  re-exported
    INCONCLUSIVE_MIME_TYPES,
    resolve_inconclusive_mime_type,
)


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
