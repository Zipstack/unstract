from enum import Enum


class ConnectorMode(Enum):
    UNKNOWN = "UNKNOWN"
    FILE_SYSTEM = "FILESYSTEM"
    DATABASE = "DATABASE"
    API = "API"
    MANUAL_REVIEW = "MANUAL_REVIEW"
