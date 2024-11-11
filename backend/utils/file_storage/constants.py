from enum import Enum


class FileStorageKeys:
    FILE_STORAGE_PROVIDER = "FILE_STORAGE_PROVIDER"
    FILE_STORAGE_CREDENTIALS = "FILE_STORAGE_CREDENTIALS"


class FileStorageType(Enum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"


class FileStorageConstants:
    PROMPT_STUDIO_FILE_PATH = "PROMPT_STUDIO_FILE_PATH"
