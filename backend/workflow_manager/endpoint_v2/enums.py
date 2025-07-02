from enum import Enum


class AllowedFileTypes(Enum):
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
    OCTET_STREAM = "application/octet-stream"

    @classmethod
    def is_allowed(cls, mime_type: str) -> bool:
        return mime_type in cls._value2member_map_


class InvalidFileTypes(Enum):
    OCTET_STREAM = "application/octet-stream"


class UncertainMimeTypes(Enum):
    OCTET_STREAM = "application/octet-stream"
    ZIP = "application/zip"

    @classmethod
    def is_uncertain(cls, mime_type: str) -> bool:
        return mime_type in cls._value2member_map_
