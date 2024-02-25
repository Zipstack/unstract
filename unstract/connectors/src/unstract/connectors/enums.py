from enum import Enum


class ConnectorMode(Enum):
    UNKNOWN = "UNKNOWN"
    FILE_SYSTEM = "FILE_SYSTEM"
    DATABASE = "DATABASE"
    API = "API"
