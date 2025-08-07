import os
from fnmatch import fnmatch


class TableColumns:
    CREATED_BY = "created_by"
    CREATED_AT = "created_at"
    PERMANENT_COLUMNS = ["created_by", "created_at"]


class DBConnectionClass:
    SNOWFLAKE = "SnowflakeDB"


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
