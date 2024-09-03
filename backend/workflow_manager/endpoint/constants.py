class TableColumns:
    CREATED_BY = "created_by"
    CREATED_AT = "created_at"
    PERMANENT_COLUMNS = ["created_by", "created_at"]


class DBConnectionClass:
    SNOWFLAKE = "SnowflakeDB"
    BIGQUERY = "BigQuery"
    MSSQL = "MSSQL"


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
    ]


class SourceConstant:
    MAX_RECURSIVE_DEPTH = 10


class ApiDeploymentResultStatus:
    SUCCESS = "Success"
    FAILED = "Failed"


class BigQuery:
    """In big query, table name has to be in the format {db}.{schema}.{table}
    Throws error if any of the params not set.

    When converted to list table size should be 3
    """

    TABLE_NAME_SIZE = 3
    COLUMN_TYPES = [
        "DATE",
        "DATETIME",
        "TIME",
        "TIMESTAMP",
    ]


class QueueResultStatus:
    SUCCESS = "Success"
    FAILED = "Failed"
