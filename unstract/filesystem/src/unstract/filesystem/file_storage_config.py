import json
import logging
import os

from unstract.sdk.file_storage import FileStorageProvider
from unstract.sdk.file_storage.fs_shared_temporary import SharedTemporaryFileStorage

from .exceptions import ProviderNotFound
from .file_storage_types import FileStorageType  # Import the shared enum

logger = logging.getLogger(__name__)


def get_provider(var_name: str, default: str = "minio") -> FileStorageProvider:
    """Retrieve the file storage provider based on an environment variable."""
    provider_name = os.environ.get(var_name, default).capitalize()
    try:
        # Attempt to map the provider name to an enum value, case-insensitively
        return FileStorageProvider[provider_name]
    except KeyError:
        allowed_providers = ", ".join(
            [provider.name for provider in FileStorageProvider]
        )
        logger.error(
            f"Invalid provider '{provider_name}'. Allowed providers: "
            f"{allowed_providers}"
        )
        raise ProviderNotFound(f"Provider '{provider_name}' not found")


# Mappings for storage types, credentials, and providers
STORAGE_MAPPING = {
    FileStorageType.WORKFLOW_EXECUTION: SharedTemporaryFileStorage,
    FileStorageType.API_EXECUTION: SharedTemporaryFileStorage,
}

FILE_STORAGE_CREDENTIALS_MAPPING = {
    FileStorageType.WORKFLOW_EXECUTION: json.loads(
        os.environ.get("WORKFLOW_EXECUTION_FS_CREDENTIAL", "{}")
    ),
    FileStorageType.API_EXECUTION: json.loads(
        os.environ.get("API_STORAGE_FS_CREDENTIAL", "{}")
    ),
}

FILE_STORAGE_PROVIDER_MAPPING = {
    FileStorageType.WORKFLOW_EXECUTION: get_provider(
        "WORKFLOW_EXECUTION_FS_PROVIDER", "minio"
    ),
    FileStorageType.API_EXECUTION: get_provider("API_STORAGE_FS_PROVIDER", "minio"),
}
