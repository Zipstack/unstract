from typing import Any

from unstract.sdk1.exceptions import FileStorageError
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider


class SharedTemporaryFileStorage(FileStorage):
    SUPPORTED_FILE_STORAGE_TYPES = [
        FileStorageProvider.MINIO.value,
        FileStorageProvider.REDIS.value,
    ]

    def __init__(
        self,
        provider: FileStorageProvider,
        **storage_config: dict[str, Any],
    ) -> None:
        """Initialize the SharedTemporaryFileStorage with validation.

        Args:
            provider: File storage provider type that must be supported for shared
                temporary storage
            **storage_config: Additional configuration parameters for the storage provider
        """
        if provider.value not in self.SUPPORTED_FILE_STORAGE_TYPES:
            raise FileStorageError(
                f"File storage provider is not supported in Shared Temporary mode. "
                f"Supported providers: {self.SUPPORTED_FILE_STORAGE_TYPES}"
            )
        if provider == FileStorageProvider.MINIO:
            super().__init__(provider, **storage_config)
        elif provider == FileStorageProvider.REDIS:
            super().__init__(provider)
        else:
            raise NotImplementedError
