from typing import Any, Union

from unstract.sdk.exceptions import FileOperationError, FileStorageError
from unstract.sdk.file_storage import FileStorage, FileStorageProvider
from unstract.sdk.file_storage.constants import Common


class PermanentFileStorage(FileStorage):
    SUPPORTED_FILE_STORAGE_TYPES = [
        FileStorageProvider.GCS.value,
        FileStorageProvider.S3.value,
        FileStorageProvider.Azure.value,
        FileStorageProvider.Local.value,
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
        if provider == FileStorageProvider.GCS:
            super().__init__(provider, credentials)
        elif provider == FileStorageProvider.Local:
            super().__init__(provider)
        else:
            raise NotImplementedError

    def _copy_on_write(self, path):
        """Copies the file to the lazily. Checks if the file is present in the
        Local File system. If yes, copies the file to the mentioned path using
        the remote file system. This is a silent copy done on need basis.

        Args:
            path (str): Path to the file

        Returns:
            NA
        """
        if not self.exists(path):
            local_file_storage = FileStorage(provider=FileStorageProvider.Local)
            if local_file_storage.exists(path):
                self.cp(path, path)

    def read(
        self,
        path: str,
        mode: str,
        encoding: str = Common.DEFAULT_ENCODING,
        seek_position: int = 0,
        length: int = Common.FULL,
    ) -> Union[bytes, str]:
        """Read the file pointed to by the file_handle.

        Args:
            path (str): Path to the file to be opened
            mode (str): Mode in whicg the file is to be opened. Usual options
                        include r, rb, w and wb
            encoding (str): Encoding type like utf-8 or utf-16
            seek_position (int): Position to start reading from
            length (int): Number of bytes to be read. Default is full
            file content.

        Returns:
            Union[bytes, str] - File contents in bytes/string based on the opened mode
        """
        try:
            # Lazy copy to the destination/remote file system
            self._copy_on_write(path)
            return super().read(path, mode, encoding, seek_position, length)
        except Exception as e:
            raise FileOperationError(str(e))
