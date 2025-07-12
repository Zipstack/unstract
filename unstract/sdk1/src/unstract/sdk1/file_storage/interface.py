from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from fsspec import AbstractFileSystem
from unstract.sdk.file_storage.constants import FileOperationParams, FileSeekPosition


class FileStorageInterface(ABC):
    @abstractmethod
    def read(
        self,
        path: str,
        mode: str,
        encoding: str = FileOperationParams.DEFAULT_ENCODING,
        seek_position: int = 0,
        length: int = FileOperationParams.READ_ENTIRE_LENGTH,
    ) -> bytes | str:
        pass

    @abstractmethod
    def write(
        self,
        path: str,
        mode: str,
        encoding: str = FileOperationParams.DEFAULT_ENCODING,
        seek_position: int = 0,
        data: bytes | str = "",
    ) -> int:
        pass

    @abstractmethod
    def seek(
        self,
        file_handle: AbstractFileSystem,
        location: int = 0,
        position: FileSeekPosition = FileSeekPosition.START,
    ) -> int:
        pass

    @abstractmethod
    def mkdir(self, path: str, create_parents: bool):
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        pass

    @abstractmethod
    def ls(self, path: str) -> list[str]:
        pass

    @abstractmethod
    def rm(self, path: str, recursive: bool = True):
        pass

    @abstractmethod
    def cp(
        self,
        lpath: str,
        rpath: str,
        recursive: bool = False,
        overwrite: bool = True,
    ):
        pass

    @abstractmethod
    def size(self, path: str) -> int:
        pass

    @abstractmethod
    def modification_time(self, path: str) -> datetime:
        pass

    @abstractmethod
    def mime_type(
        self,
        path: str,
        read_length: int = FileOperationParams.READ_ENTIRE_LENGTH,
    ) -> str:
        pass

    @abstractmethod
    def download(self, from_path: str, to_path: str):
        pass

    @abstractmethod
    def glob(self, path: str) -> list[str]:
        pass

    @abstractmethod
    def get_hash_from_file(self, path: str) -> str:
        pass

    @abstractmethod
    def json_dump(
        self,
        path: str,
        data: dict[str, Any],
        **kwargs: dict[Any, Any],
    ):
        pass

    @abstractmethod
    def yaml_dump(
        self,
        path: str,
        data: dict[str, Any],
        **kwargs: dict[Any, Any],
    ):
        pass

    @abstractmethod
    def json_load(self, path: str) -> dict[Any, Any]:
        pass

    @abstractmethod
    def yaml_load(
        self,
        path: str,
    ) -> dict[Any, Any]:
        pass

    @abstractmethod
    def guess_extension(self, path: str) -> str:
        pass

    @abstractmethod
    def walk(self, path: str):
        pass
