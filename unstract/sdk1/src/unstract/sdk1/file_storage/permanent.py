import logging
from typing import Any

import filetype
import magic
from unstract.sdk.exceptions import FileOperationError, FileStorageError
from unstract.sdk.file_storage.constants import FileOperationParams
from unstract.sdk.file_storage.impl import FileStorage
from unstract.sdk.file_storage.provider import FileStorageProvider

logger = logging.getLogger(__name__)


class PermanentFileStorage(FileStorage):
    SUPPORTED_FILE_STORAGE_TYPES = [
        FileStorageProvider.GCS.value,
        FileStorageProvider.S3.value,
        FileStorageProvider.MINIO.value,
        FileStorageProvider.LOCAL.value,
        FileStorageProvider.AZURE.value,
    ]

    def __init__(
        self,
        provider: FileStorageProvider,
        **storage_config: dict[str, Any],
    ):
        if provider.value not in self.SUPPORTED_FILE_STORAGE_TYPES:
            raise FileStorageError(
                f"File storage provider `{provider.value}` is not "
                f"supported in Permanent mode. "
                f"Supported providers: {self.SUPPORTED_FILE_STORAGE_TYPES}"
            )
        if (
            provider == FileStorageProvider.GCS
            or provider == FileStorageProvider.LOCAL
            or provider == FileStorageProvider.MINIO
            or provider == FileStorageProvider.S3
            or provider == FileStorageProvider.AZURE
        ):
            super().__init__(provider, **storage_config)
        else:
            raise NotImplementedError(f"Provider {provider.value} is not implemented")

    def _copy_on_read(self, path: str, legacy_storage_path: str):
        """Copies the file to the remote storage lazily if not present already.
        Checks if the file is present in the Local File system. If yes, copies
        the file to the mentioned path using the remote file system. This is a
        silent copy done on need basis.

        Args:
            path (str): Path to the file
            legacy_storage_path (str): Legacy path to the same file

        Returns:
            NA
        """
        # If path does not exist on remote storage
        if not self.exists(path):
            local_file_storage = FileStorage(provider=FileStorageProvider.LOCAL)
            local_file_path = legacy_storage_path
            # If file exists on local storage, then migrate the file
            # to remote storage
            if local_file_storage.exists(local_file_path):
                self.upload(local_file_path, path)
                logger.info(
                    f"Uploading {local_file_path} from "
                    f"{local_file_storage.provider} to remote "
                    f"storage {self.provider} in the path {path}"
                )

    def read(
        self,
        path: str,
        mode: str,
        encoding: str = FileOperationParams.DEFAULT_ENCODING,
        seek_position: int = 0,
        length: int = FileOperationParams.READ_ENTIRE_LENGTH,
        legacy_storage_path: str | None = None,
    ) -> bytes | str:
        """Read the file pointed to by the file_handle.

        Args:
            path (str): Path to the file to be opened
            mode (str): Mode in whicg the file is to be opened. Usual options
                        include r, rb, w and wb
            encoding (str): Encoding type like utf-8 or utf-16
            seek_position (int): Position to start reading from
            length (int): Number of bytes to be read. Default is full
            file content.
            legacy_storage_path (str):  Legacy path to the same file

        Returns:
            Union[bytes, str] - File contents in bytes/string based on the opened mode
        """
        try:
            # Lazy copy to the destination/remote file system
            if legacy_storage_path:
                self._copy_on_read(path, legacy_storage_path)
            return super().read(path, mode, encoding, seek_position, length)
        except Exception as e:
            if isinstance(e, FileNotFoundError) or isinstance(e, FileOperationError):
                raise e
            raise FileOperationError(str(e)) from e

    def mime_type(
        self,
        path: str,
        read_length: int = FileOperationParams.READ_ENTIRE_LENGTH,
        legacy_storage_path: str | None = None,
    ) -> str:
        """Gets the file MIME type for an input file. Uses libmagic to perform
        the same.

        Args:
            path (str): Path of the input file
            read_length (int): Length(bytes) to be read from the file for in
            order to identify the mime type. Defaults to read the entire length.
            legacy_storage_path (str):  Legacy path to the same file

        Returns:
            str: MIME type of the file
        """
        sample_contents = self.read(
            path=path,
            mode="rb",
            length=read_length,
            legacy_storage_path=legacy_storage_path,
        )
        mime_type = magic.from_buffer(sample_contents, mime=True)
        return mime_type

    def guess_extension(self, path: str, legacy_storage_path: str | None = None) -> str:
        """Returns the extension of the file passed.

        Args:
            path (str): String holding the path
            legacy_storage_path (str):  Legacy path to the same file

        Returns:
            str: File extension
        """
        file_extension = ""
        sample_contents = self.read(
            path=path,
            mode="rb",
            length=FileOperationParams.EXTENSION_DEFAULT_READ_LENGTH,
            legacy_storage_path=legacy_storage_path,
        )
        if sample_contents:
            file_type = filetype.guess(sample_contents)
            file_extension = file_type.EXTENSION
        return file_extension
