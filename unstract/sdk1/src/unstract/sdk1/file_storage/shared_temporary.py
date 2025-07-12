from typing import Any

from unstract.sdk.exceptions import FileStorageError
from unstract.sdk.file_storage import FileStorage, FileStorageProvider


class SharedTemporaryFileStorage(FileStorage):
    SUPPORTED_FILE_STORAGE_TYPES = [
        FileStorageProvider.MINIO.value,
        FileStorageProvider.REDIS.value,
    ]

    def __init__(
        self,
        provider: FileStorageProvider,
        **storage_config: dict[str, Any],
    ):
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
