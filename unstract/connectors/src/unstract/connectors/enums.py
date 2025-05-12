from enum import Enum


class ConnectorMode(Enum):
    UNKNOWN = "UNKNOWN"
    FILE_SYSTEM = "FILE_SYSTEM"
    DATABASE = "DATABASE"
    API = "API"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    EMAIL = "EMAIL"
