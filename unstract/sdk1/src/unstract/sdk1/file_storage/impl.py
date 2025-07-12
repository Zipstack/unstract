import json
import logging
from datetime import datetime
from hashlib import sha256
from typing import Any

import filetype
import fsspec
import magic
import yaml
from unstract.sdk.exceptions import FileOperationError
from unstract.sdk.file_storage.constants import FileOperationParams, FileSeekPosition
from unstract.sdk.file_storage.helper import FileStorageHelper, skip_local_cache
from unstract.sdk.file_storage.interface import FileStorageInterface
from unstract.sdk.file_storage.provider import FileStorageProvider

logger = logging.getLogger(__name__)


class FileStorage(FileStorageInterface):
    # This class integrates fsspec library for file operations

    fs: fsspec  # fsspec file system handle
    provider: FileStorageProvider

    def __init__(self, provider: FileStorageProvider, **storage_config: dict[str, Any]):
        self.fs = FileStorageHelper.file_storage_init(provider, **storage_config)
        self.provider = provider

    @skip_local_cache
    def read(
        self,
        path: str,
        mode: str,
        encoding: str = FileOperationParams.DEFAULT_ENCODING,
        seek_position: int = 0,
        length: int = FileOperationParams.READ_ENTIRE_LENGTH,
    ) -> bytes | str:
        """Read the file pointed to by the file_handle.

        Args:
            path (str): Path to the file to be opened
            mode (str): Mode in which the file is to be opened. Usual options
                        include r, rb, w and wb
            encoding (str): Encoding type like utf-8 or utf-16
            seek_position (int): Position to start reading from
            length (int): Number of bytes to be read. Default is full
            file content.

        Returns:
            Union[bytes, str] - File contents in bytes/string based on the opened mode
        """
        with self.fs.open(path=path, mode=mode, encoding=encoding) as file_handle:
            if seek_position > 0:
                file_handle.seek(seek_position)
            return file_handle.read(length)

    def write(
        self,
        path: str,
        mode: str,
        encoding: str = FileOperationParams.DEFAULT_ENCODING,
        seek_position: int = 0,
        data: bytes | str = "",
    ) -> int:
        """Write data in the file pointed to by the file-handle.

        Args:
            path (str): Path to the file to be opened
            mode (str): Mode in whicg the file is to be opened. Usual options
                        include r, rb, w and wb
            encoding (str): Encoding type like utf-8 or utf-16
            seek_position (int): Position to start writing from
            data (Union[bytes, str]): Contents to be written

        Returns:
            int: Number of bytes that were successfully written to the file
        """
        try:
            with self.fs.open(path=path, mode=mode, encoding=encoding) as file_handle:
                return file_handle.write(data)
        except Exception as e:
            raise FileOperationError(str(e)) from e

    @skip_local_cache
    def seek(
        self,
        path: str,
        location: int = 0,
        position: FileSeekPosition = FileSeekPosition.START,
    ) -> int:
        """Place the file pointer to the mentioned location in the file
        relative to the position.

        Args:
            path (str): path of the file
            location (int): Nth byte position. To be understood in relation to
            the arg "position"
            position (FileSeekPosition): from start of file, current location
            or end of file

        Returns:
            int: file pointer location after seeking to the mentioned position
        """
        with self.fs.open(path=path, mode="rb") as file_handle:
            return file_handle.seek(location, position)

    def mkdir(self, path: str, create_parents: bool = True):
        """Create a directory.

        Args:
            path (str): Path of the directory to be created
            create_parents (bool): Specify if parent directories to be created
            if any of the nested directory does not exist
        """
        try:
            self.fs.mkdir(path=path, create_parents=create_parents)
        except FileExistsError:
            logger.debug(f"Path {path} already exists.")
        except Exception as e:
            raise FileOperationError(str(e)) from e

    @skip_local_cache
    def exists(self, path: str) -> bool:
        """Checks if a file/directory path exists.

        Args:
            path (str): File/directory path

        Returns:
            bool: If the file/directory  exists or not
        """
        try:
            return self.fs.exists(path)
        except Exception as e:
            raise FileOperationError(str(e)) from e

    @skip_local_cache
    def ls(self, path: str) -> list[str]:
        """List the directory path.

        Args:
            path (str): Directory path

        Returns:
            List[str]: List of files / directories under the path
        """
        return self.fs.ls(path)

    @skip_local_cache
    def rm(self, path: str, recursive: bool = True):
        """Removes a file or directory mentioned in path.

        Args:
            path (str): Path to the file / directory
            recursive (bool): Whether the files and folders nested
            under path are to be removed or not

        Returns:
            NA
        """
        return self.fs.rm(path=path, recursive=recursive)

    @skip_local_cache
    def cp(
        self,
        src: str,
        dest: str,
        recursive: bool = False,
        overwrite: bool = True,
    ):
        """Copies files from source(lpath) path to the destination(rpath) path.

        Args:
            src (str): Path to the source
            dest (str): Path to the destination
            recursive (bool): Copy recursively when set to True
            overwrite (bool): Overwrite existing path with same name

        Returns:
            NA
        """
        return self.fs.cp(src, dest, recursive=recursive, overwrite=overwrite)

    @skip_local_cache
    def size(self, path: str) -> int:
        """Get the size of the file specified in path.

        Args:
            path (str): Path to the file

        Returns:
            int: Size of the file in bytes
        """
        file_info = self.fs.info(path)
        return file_info["size"]

    @skip_local_cache
    def modification_time(self, path: str) -> datetime:
        """Get the last modification time of the file specified in path.

        Args:
            path (str): Path to the file

        Returns:
            datetime: Last modified time in datetime
        """
        file_info = self.fs.info(path)

        # Try different possible timestamp keys
        file_mtime = None
        for key in ["mtime", "LastModified", "last_modified"]:
            file_mtime = file_info.get(key)
            if file_mtime is not None:
                break

        if file_mtime is None:
            raise FileOperationError(
                f"Could not find modification time in file info: {file_info}"
            )

        if isinstance(file_mtime, datetime):
            return file_mtime

        return datetime.fromtimestamp(file_mtime)

    def mime_type(
        self,
        path: str,
        read_length: int = FileOperationParams.READ_ENTIRE_LENGTH,
    ) -> str:
        """Gets the file MIME type for an input file. Uses libmagic to perform
        the same.

        Args:
            path (str): Path of the input file
            read_length (int): Length(bytes) to be read from the file for in
            order to identify the mime type. Defaults to read the entire length.

        Returns:
            str: MIME type of the file
        """
        sample_contents = self.read(path=path, mode="rb", length=read_length)
        mime_type = magic.from_buffer(sample_contents, mime=True)
        return mime_type

    @skip_local_cache
    def download(self, from_path: str, to_path: str):
        """Downloads the file mentioned in from_path to to_path on the local
        system. The instance calling the method needs to be the FileStorage
        initialised with the remote file system.

        Args:
            from_path (str): Path of the file to be downloaded (remote)
            to_path (str): Path where the file is to be downloaded
            on local system

        Returns:
            NA
        """
        self.fs.get(rpath=from_path, lpath=to_path)

    @skip_local_cache
    def upload(self, from_path: str, to_path: str):
        """Uploads the file mentioned in from_path (local system) to to_path
        (remote system). The instance calling the method needs to be the
        FileStorage initialised with the remote file system where the file
        needs to be uploaded.

        Args:
            from_path (str): Path of the file to be uploaded (local)
            to_path (str): Path where the file is to be uploaded (usually remote)

        Returns:
            NA
        """
        self.fs.put(from_path, to_path)

    def glob(self, path: str) -> list[str]:
        """Lists files under path matching the pattern sepcified as part of
        path in the argument.

        Args:
            path (str): path to the directory where files matching the
            specified pattern is to be found
            Eg. a/b/c/*.txt will list all txt files under a/b/c/

        Returns:
            list[str]: List of file names matching any pattern specified
        """
        try:
            return self.fs.glob(path)
        except Exception as e:
            raise FileOperationError(str(e)) from e

    @skip_local_cache
    def get_hash_from_file(self, path: str) -> str:
        """Computes the hash for a file.

        Uses sha256 to compute the file hash through a buffered read.

        Args:
            file_path (str): Path to file that needs to be hashed

        Returns:
            str: SHA256 hash of the file
        """
        h = sha256()
        b = bytearray(128 * 1024)
        mv = memoryview(b)
        with self.fs.open(path) as f:
            while n := f.readinto(mv):
                h.update(mv[:n])
        return str(h.hexdigest())

    def json_dump(
        self,
        path: str,
        data: dict[str, Any],
        **kwargs: dict[Any, Any],  # type: ignore
    ):
        """Dumps data into the given file specified by path.

        Args:
            path (str): Path to file where JSON is to be dumped
            data (dict): Object to be written to the file
            **kwargs (dict): Any other additional arguments
        """
        try:
            with self.fs.open(path=path, mode="w", encoding="utf-8") as f:
                json.dump(obj=data, fp=f, **kwargs)  # type: ignore
        except Exception as e:
            raise FileOperationError(str(e)) from e

    def yaml_dump(
        self,
        path: str,
        data: dict[str, Any],
        **kwargs: dict[Any, Any],  # type: ignore
    ):
        """Dumps data into the given file specified by path.

        Args:
            path (str): Path to file where yml is to be dumped
            data (dict): Object to be written to the file
            **kwargs (dict): Any other additional arguments
        """
        try:
            with self.fs.open(path=path, mode="w", encoding="utf-8") as f:
                yaml.dump(data=data, stream=f, **kwargs)  # type: ignore
        except Exception as e:
            raise FileOperationError(str(e)) from e

    @skip_local_cache
    def json_load(self, path: str) -> dict[Any, Any]:
        with self.fs.open(path=path) as json_file:
            data: dict[str, Any] = json.load(json_file)
            return data

    @skip_local_cache
    def yaml_load(
        self,
        path: str,
    ) -> dict[Any, Any]:
        """Loads data from a file as yaml.

        Args:
            path (str): Path to file where yml is to be loaded

        Returns:
            dict[Any, Any]: Data loaded as yaml
        """
        with self.fs.open(path=path) as f:
            data: dict[str, Any] = yaml.safe_load(f)
            return data

    def guess_extension(self, path: str) -> str:
        """Returns the extension of the file passed.

        Args:
            path (str): String holding the path

        Returns:
            str: File extension
        """
        file_extension = ""
        sample_contents = self.read(
            path=path,
            mode="rb",
            length=FileOperationParams.EXTENSION_DEFAULT_READ_LENGTH,
        )
        if sample_contents:
            file_type = filetype.guess(sample_contents)
            file_extension = file_type.EXTENSION
        return file_extension

    def walk(self, path: str, max_depth=None, topdown=True):
        """Walks the dir in the path and returns the list of files/dirs.

        Args:
            path (str): Root to recurse into
            maxdepth (int): Maximum recursion depth. None means limitless,
            but not recommended
                on link-based file-systems.
            topdown (bool): Whether to walk the directory tree from the top
            downwards or from
                the bottom upwards.

        Returns:
            Iterator containing the list of files and folders
        """
        # Invalidating cache explicitly to avoid any stale listing
        self.fs.invalidate_cache(path=path)
        return self.fs.walk(path, maxdepth=max_depth, topdown=topdown)
