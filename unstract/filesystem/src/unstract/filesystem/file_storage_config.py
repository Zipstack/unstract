import logging
import os

from unstract.flags.feature_flag import check_feature_flag_status

from .exceptions import ProviderNotFound
from .file_storage_types import FileStorageType  # Import the shared enum

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.file_storage import FileStorageProvider, StorageType
else:
    from unstract.sdk.file_storage import FileStorageProvider, StorageType


logger = logging.getLogger(__name__)


def get_provider(var_name: str, default: str = "minio") -> FileStorageProvider:
    """Retrieve the file storage provider based on an environment variable."""
    provider_name = os.environ.get(var_name, default).upper()
    try:
        # Attempt to map the provider name to an enum value, case-insensitively
        return FileStorageProvider[provider_name]
    except KeyError:
        allowed_providers = ", ".join([provider.name for provider in FileStorageProvider])
        logger.error(
            f"Invalid provider '{provider_name}'. Allowed providers: "
            f"{allowed_providers}"
        )
        raise ProviderNotFound(f"Provider '{provider_name}' not found")


# Mappings for storage types, credentials, and providers
STORAGE_MAPPING = {
    FileStorageType.WORKFLOW_EXECUTION: StorageType.SHARED_TEMPORARY,
    FileStorageType.API_EXECUTION: StorageType.SHARED_TEMPORARY,
}

FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING = {
    FileStorageType.WORKFLOW_EXECUTION: "WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS",
    FileStorageType.API_EXECUTION: "API_FILE_STORAGE_CREDENTIALS",
}
