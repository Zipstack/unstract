import base64
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import magic
from connector_v2.models import ConnectorInstance
from deprecated import deprecated
from django.conf import settings
from django.http import StreamingHttpResponse
from file_management.exceptions import (
    ConnectorApiRequestError,
    ConnectorClassNotFound,
    FileDeletionFailed,
    FileListError,
    FileNotFound,
    InvalidFileType,
    MissingConnectorParams,
    OrgIdNotValid,
    TenantDirCreationError,
)
from file_management.file_management_dto import FileInformation
from fsspec import AbstractFileSystem
from pydrive2.files import ApiRequestError

from unstract.connectors.filesystems import connectors as fs_connectors
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


class FileManagerHelper:

    @staticmethod
    def get_file_system(connector: ConnectorInstance) -> UnstractFileSystem:
        """Creates the `UnstractFileSystem` for the corresponding connector."""
        metadata = connector.metadata
        if connector.connector_id in fs_connectors:
            connector = fs_connectors[connector.connector_id]["metadata"]["connector"]
            connector_class: UnstractFileSystem = connector(metadata)
            return connector_class
        else:
            logger.error(f"Class not Found for {connector.connector_id}")
            raise ConnectorClassNotFound

    @staticmethod
    def list_files(file_system: UnstractFileSystem, path: str) -> list[FileInformation]:
        fs = file_system.get_fsspec_fs()
        file_path = f"{path}"
        # TODO: Add below logic by checking each connector?
        try:
            if file_system.path and (not path or path == "/"):
                file_path = file_system.path
        except AttributeError:
            if hasattr(fs, "path") and fs.path and (not path or path == "/"):
                file_path = fs.path
        except Exception:
            logger.error(f"Missing path Atribute in {fs}")
            raise MissingConnectorParams()

        try:
            return FileManagerHelper.get_files(fs, file_path)
        except Exception as e:
            msg = f"Error listing files. {e}"
            logger.error(msg)
            raise FileListError(msg)

    @staticmethod
    def get_files(fs: AbstractFileSystem, file_path: str) -> list[FileInformation]:
        """Iterate through the directories and make a list of
        FileInformation."""
        if not file_path.endswith("/"):
            file_path += "/"

        files = fs.ls(file_path, detail=True)
        file_list = []
        for file_info in files:
            file_name = file_info.get("name")
            if os.path.normpath(file_path) == os.path.normpath(file_name):
                continue

            # Call fs.info() to get file size if its missing
            if file_info.get("type") == "file" and file_info.get("size") is None:
                file_info = fs.info(file_name)

            file_content_type = file_info.get("ContentType")
            if not file_content_type:
                file_content_type, _ = mimetypes.guess_type(file_name)
            file_list.append(FileInformation(file_info, file_content_type))
        return file_list

    @staticmethod
    def download_file(
        file_system: UnstractFileSystem, file_path: str
    ) -> StreamingHttpResponse:
        fs = file_system.get_fsspec_fs()
        file_info = fs.info(file_path)
        file_name = file_info.get("name")
        base_name = os.path.basename(file_name)

        file_content_type = file_info.get("ContentType")
        file_type = file_info.get("type")
        if file_type != "file":
            raise InvalidFileType
        try:
            if not file_content_type:
                file_content_type, _ = mimetypes.guess_type(file_path)
            if not file_content_type:
                file = fs.open(file_path, "rb", block_size=500)
                file_content_type = magic.from_buffer(file.read(), mime=True)
                file.close()

            file = fs.open(file_path, "rb")
            response = StreamingHttpResponse(file, content_type=file_content_type)
            response["Content-Disposition"] = f"attachment; filename={base_name}"
            return response
        except ApiRequestError as exception:
            logger.error(f"ApiRequestError from {file_info} {exception}")
            raise ConnectorApiRequestError

    @staticmethod
    def upload_file(
        file_system: UnstractFileSystem, path: str, file: Any, file_name: str
    ) -> None:
        fs = file_system.get_fsspec_fs()

        file_path = f"{path}"
        try:
            if file_system.path and (not path or path == "/"):
                file_path = f"{file_system.path}/"
        except AttributeError:
            if fs.path and (not path or path == "/"):
                file_path = f"{fs.path}/"

        file_path = file_path + "/" if not file_path.endswith("/") else file_path

        # adding filename with path
        file_path += file_name
        with fs.open(file_path, mode="wb") as remote_file:
            if isinstance(file, bytes):
                remote_file.write(file)
            else:
                remote_file.write(file.read())

    @staticmethod
    @deprecated(reason="Use remote FS APIs from SDK")
    def fetch_file_contents(
        file_system: UnstractFileSystem,
        file_path: str,
        allowed_content_types: list[str],
    ) -> Any:
        fs = file_system.get_fsspec_fs()

        try:
            file_info = fs.info(file_path)
        except FileNotFoundError:
            raise FileNotFound

        file_content_type = file_info.get("ContentType")
        file_type = file_info.get("type")

        if file_type != "file":
            raise InvalidFileType

        try:
            if not file_content_type:
                file_content_type, _ = mimetypes.guess_type(file_path)
            if not file_content_type:
                file = fs.open(file_path, "rb", block_size=500)
                file_content_type = magic.from_buffer(file.read(), mime=True)
                file.close()

        except ApiRequestError as exception:
            logger.error(f"ApiRequestError from {file_info} {exception}")
            raise ConnectorApiRequestError

        data = ""

        # Handle allowed file types
        if file_content_type == "application/pdf":
            with fs.open(file_path, "rb") as file:
                data = base64.b64encode(file.read())

        elif file_content_type == "text/plain":
            with fs.open(file_path, "r") as file:
                logger.info(f"Reading text file: {file_path}")
                data = file.read()

        # Check if the file type is in the allowed list
        elif file_content_type not in allowed_content_types:
            raise InvalidFileType(f"File type '{file_content_type}' is not allowed.")

        else:
            logger.warning(f"File type '{file_content_type}' is not handled.")

        return {"data": data, "mime_type": file_content_type}

    @staticmethod
    def _delete_file(fs, file_path):
        try:
            fs.rm(file_path)
        except FileNotFoundError:
            logger.info(f"File not found: {file_path}")
        except Exception as e:
            logger.info(f"Unable to delete file {e}")
            raise FileDeletionFailed(f"Unable to delete file {e}")

    @staticmethod
    def _get_base_path(file_system: UnstractFileSystem, path: str):
        fs = file_system.get_fsspec_fs()
        base_path = getattr(
            file_system if hasattr(file_system, "path") else fs, "path", path
        )
        base_path = base_path.rstrip("/") + "/"
        return base_path

    @staticmethod
    def delete_file(file_system: UnstractFileSystem, path: str, file_name: str) -> bool:
        fs = file_system.get_fsspec_fs()
        base_path = FileManagerHelper._get_base_path(file_system, path)
        file_path = str(Path(base_path) / file_name)
        FileManagerHelper._delete_file(fs, file_path)
        return True

    @staticmethod
    def delete_related_files(
        file_system: UnstractFileSystem,
        path: str,
        file_name: str,
        directories: list[str],
    ) -> bool:
        fs = file_system.get_fsspec_fs()
        base_path = FileManagerHelper._get_base_path(file_system, path)
        base_file_name, _ = os.path.splitext(file_name)
        pattern = f"{base_file_name}.*"
        file_paths = FileManagerHelper._find_files(fs, base_path, directories, pattern)
        for file_path in file_paths:
            FileManagerHelper._delete_file(fs, file_path)
        return True

    @staticmethod
    def _find_files(fs, base_path: str, directories: list[str], pattern: str):
        file_paths = []
        for directory in directories:
            directory_path = str(Path(base_path) / directory)
            for file in fs.glob(f"{directory_path}/{pattern}"):
                file_paths.append(file)
        return file_paths

    @staticmethod
    def handle_sub_directory_for_tenants(
        org_id: str, user_id: str, tool_id: str, is_create: bool
    ) -> str:
        """Resolves a directory path meant for a user running prompt studio.

        Args:
            org_id (str): Organization ID
            user_id (str): User ID
            tool_id (str): ID of the prompt studio tool
            is_create (bool): Flag to create the directory

        Returns:
            str: The absolute path to the directory meant for prompt studio
        """
        if not org_id:
            raise OrgIdNotValid()
        base_path = Path(settings.PROMPT_STUDIO_FILE_PATH)
        file_path: Path = base_path / org_id / user_id / tool_id
        extract_file_path: Path = Path(file_path, "extract")
        summarize_file_path: Path = Path(file_path, "summarize")
        if is_create:
            try:
                os.makedirs(file_path, exist_ok=True)
                os.makedirs(extract_file_path, exist_ok=True)
                os.makedirs(summarize_file_path, exist_ok=True)
            except OSError as e:
                logger.error(f"Error while creating {file_path}: {e}")
                raise TenantDirCreationError
        return str(file_path)
