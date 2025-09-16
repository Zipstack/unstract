import logging
import os
from enum import Enum
from fnmatch import fnmatch
from typing import Any

logger = logging.getLogger(__name__)


class TableColumns:
    CREATED_BY = "created_by"
    CREATED_AT = "created_at"
    METADATA = "metadata"
    ERROR_MESSAGE = "error_message"
    STATUS = "status"
    USER_FIELD_1 = "user_field_1"
    USER_FIELD_2 = "user_field_2"
    USER_FIELD_3 = "user_field_3"
    PERMANENT_COLUMNS = [
        "created_by",
        "created_at",
        "metadata",
        "error_message",
        "status",
        "user_field_1",
        "user_field_2",
        "user_field_3",
    ]


class DBConnectionClass:
    SNOWFLAKE = "SnowflakeDB"
    BIGQUERY = "BigQuery"


class Snowflake:
    COLUMN_TYPES = [
        "VARCHAR",
        "CHAR",
        "CHARACTER",
        "STRING",
        "TEXT",
        "BINARY",
        "VARBINARY",
        "DATE",
        "DATETIME",
        "TIME",
        "TIMESTAMP",
        "TIMESTAMP_LTZ",
        "TIMESTAMP_NTZ",
        "TIMESTAMP_TZ",
        "BOOLEAN",
    ]


class FileSystemConnector:
    MAX_FILES = 100


class WorkflowFileType:
    SOURCE = "SOURCE"
    INFILE = "INFILE"
    METADATA_JSON = "METADATA.json"


class SourceKey:
    FILE_EXTENSIONS = "fileExtensions"
    PROCESS_SUB_DIRECTORIES = "processSubDirectories"
    MAX_FILES = "maxFiles"
    FOLDERS = "folders"
    FILE_PROCESSING_ORDER = "fileProcessingOrder"


class FileProcessingOrder(str, Enum):
    """File processing order for SourceKey.FILE_PROCESSING_ORDER.

    Semantics:
    - oldest_first: ascending last-modified time (mtime).
    - newest_first: descending mtime.
    - unordered: no explicit ordering (OS enumeration order; may be nondeterministic).
    """

    UNORDERED = "unordered"
    OLDEST_FIRST = "oldest_first"  # FIFO
    NEWEST_FIRST = "newest_first"  # LIFO

    @classmethod
    def values(cls) -> list[str]:
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

        # Already an enum instance
        if isinstance(value, cls):
            return value

        # Try to convert string to enum
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                logger.warning(
                    f"Invalid file processing order '{value}', using {default.value}"
                )
                return default

        return default


class DestinationKey:
    TABLE = "table"
    INCLUDE_AGENT = "includeAgent"
    INCLUDE_TIMESTAMP = "includeTimestamp"
    AGENT_NAME = "agentName"
    COLUMN_MODE = "columnMode"
    SINGLE_COLUMN_NAME = "singleColumnName"
    PATH = "path"
    OUTPUT_FOLDER = "outputFolder"
    OVERWRITE_OUTPUT_DOCUMENT = "overwriteOutput"
    FILE_PATH = "filePath"
    EXECUTION_ID = "executionId"


class OutputJsonKey:
    JSON_RESULT_KEY = "result"


class FileType:
    PDF_DOCUMENTS = "PDF documents"
    TEXT_DOCUMENTS = "Text documents"
    IMAGES = "Images"


class FilePattern:
    PDF_DOCUMENTS = ["*.pdf"]
    TEXT_DOCUMENTS = ["*.txt", "*.doc", "*.docx"]
    IMAGES = [
        "*.jpg",
        "*.jpeg",
        "*.png",
        "*.gif",
        "*.bmp",
        "*.tif",
        "*.tiff",
        "*.webp",
    ]
    SPREADSHEETS = ["*.xls", "*.xlsx", "*.ods"]
    PRESENTATIONS = ["*.ppt", "*.pptx", "*.odp"]
    OPEN_DOCS = ["*.odt"]
    DATA_FILES = ["*.csv", "*.json"]
    OTHER_FILES = ["*.cdfv2"]

    @classmethod
    def get_supported_extensions(cls) -> list[str]:
        """Aggregate all supported file extensions."""
        return [
            *cls.PDF_DOCUMENTS,
            *cls.TEXT_DOCUMENTS,
            *cls.IMAGES,
            *cls.SPREADSHEETS,
            *cls.PRESENTATIONS,
            *cls.OPEN_DOCS,
            *cls.DATA_FILES,
            *cls.OTHER_FILES,
        ]

    @classmethod
    def is_supported(cls, filename: str) -> bool:
        """Check if the file extension of the given filename is supported."""
        _, ext = os.path.splitext(filename)
        if not ext:
            return True  # allow files with no extension
        return any(
            fnmatch(filename.lower(), pattern)
            for pattern in cls.get_supported_extensions()
        )


class SourceConstant:
    MAX_RECURSIVE_DEPTH = 10


class ApiDeploymentResultStatus:
    SUCCESS = "Success"
    FAILED = "Failed"


class QueueResultStatus:
    SUCCESS = "Success"
    FAILED = "Failed"
