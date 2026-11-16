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

    Keep in sync with LLMWhisperer's supported types, and with the copy in the
    workers package.
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

        Any `text/*` passes; html, xml, tsv and the like reach the extractor as
        text rather than as listed formats.
        """
        if mime_type.startswith("text/"):
            return True
        return mime_type in cls._value2member_map_
