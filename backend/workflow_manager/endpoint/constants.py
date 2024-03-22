import datetime
from typing import Any, Optional


class TableColumns:
    CREATED_BY = "created_by"
    CREATED_AT = "created_at"
    PERMANENT_COLUMNS = ["created_by", "created_at"]


class DBConnectionClass:
    SNOWFLAKE = "SnowflakeConnection"
    BIGQUERY = "Client"


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
    ROOT_FOLDER = "rootFolder"


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


class OutputJsonKey:
    JSON_RESULT_KEY = "result"


class FileType:
    PDF_DOCUMENTS = "PDF documents"
    TEXT_DOCUMENTS = "Text documents"
    WORD_DOCUMENTS = "Word documents"
    OPENOFFICE_DOCUMENTS = "Openoffice documents"
    IMAGES = "Images"


class FilePattern:
    PDF_DOCUMENTS = ["*.pdf"]
    TEXT_DOCUMENTS = ["*.txt"]
    WORD_DOCUMENTS = ["*.doc", "*.docx"]
    OPENOFFICE_DOCUMENTS = ["*.odt"]
    IMAGES = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]


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


class DBConnectorTypeConverter:
    """_summary_

    Class to convert python data type to corresponding connector
    database data type
    """

    @staticmethod
    def python_to_sql_mapping(python_type: Any) -> Optional[str]:
        """Method used to convert python to SQL datatype Used by Postgres,
        Redshift, Snowflake."""
        mapping = {
            str: "VARCHAR(255)",
            int: "INT",
            float: "FLOAT",
            datetime.datetime: "TIMESTAMP",
        }
        return mapping.get(python_type, "VARCHAR(255)")

    @staticmethod
    def python_to_bigquery_mapping(python_type: Any) -> Optional[str]:
        """Method used to convert python to bigquery datatype."""
        mapping = {
            str: "string",
            int: "INT64",
            float: "FLOAT64",
            datetime.datetime: "TIMESTAMP",
        }
        return mapping.get(python_type, "string")
