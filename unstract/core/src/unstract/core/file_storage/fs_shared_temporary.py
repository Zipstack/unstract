from typing import Any, Union

from unstract.sdk.exceptions import FileStorageError
from unstract.sdk.file_storage import FileStorage, FileStorageProvider


class SharedTemporaryFileStorage(FileStorage):
    SUPPORTED_FILE_STORAGE_TYPES = [
        FileStorageProvider.Minio.value,
        FileStorageProvider.Redis.value,
    ]

    def __init__(
        self,
        provider: FileStorageProvider,
        credentials: Union[dict[str, Any], None] = None,
    ):
        if provider.value not in self.SUPPORTED_FILE_STORAGE_TYPES:
            raise FileStorageError(
                f"File storage provider is not supported in Permanent mode. "
                f"Supported providers: {self.SUPPORTED_FILE_STORAGE_TYPES}"
            )
        if provider == FileStorageProvider.Minio:
            super().__init__(provider, credentials)
        elif provider == FileStorageProvider.Redis:
            super().__init__(provider)
        else:
            raise NotImplementedError
