import base64
import logging
import os
from pathlib import Path
from typing import Any, Union

from file_management.file_management_helper import FileManagerHelper
from unstract.sdk.file_storage import FileStorage
from unstract.sdk.file_storage.constants import StorageType
from unstract.sdk.file_storage.env_helper import EnvHelper
from utils.file_storage.constants import FileStorageConstants, FileStorageKeys

from unstract.core.utilities import UnstractUtils

logger = logging.getLogger(__name__)


class PromptStudioFileHelper:
    @staticmethod
    def get_or_create_prompt_studio_subdirectory(
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
        base_path = UnstractUtils.get_env(
            env_key=FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH
        )
        file_path = str(Path(base_path) / org_id / user_id / tool_id)
        extract_file_path = str(Path(file_path) / "extract")
        summarize_file_path = str(Path(file_path) / "summarize")
        if is_create:
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )
            fs_instance.mkdir(file_path, create_parents=True)
            fs_instance.mkdir(extract_file_path, create_parents=True)
            fs_instance.mkdir(summarize_file_path, create_parents=True)
        return str(file_path)

    @staticmethod
    def upload_for_ide(
        org_id: str, user_id: str, tool_id: str, uploaded_file: Any
    ) -> None:
        """Uploads the file to a remote storage

        Args:
            org_id (str): Organization ID
            user_id (str): User ID
            tool_id (str): ID of the prompt studio tool
            uploaded_file : File to upload to remote
        """
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        file_system_path = (
            PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
                org_id=org_id,
                is_create=True,
                user_id=user_id,
                tool_id=str(tool_id),
            )
        )
        file_path = str(Path(file_system_path) / uploaded_file.name)
        fs_instance.write(path=file_path, mode="wb", data=uploaded_file.read())

    @staticmethod
    def fetch_file_contents(
        org_id: str, user_id: str, tool_id: str, file_name: str
    ) -> Union[bytes, str]:
        """Method to fetch file contents from the remote location.
        The path is constructed in runtime based on the args"""
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        # Fetching legacy file path for lazy copy
        # This has to be removed once the usage of FS APIs
        # are standadized.
        legacy_file_system_path = FileManagerHelper.handle_sub_directory_for_tenants(
            org_id=org_id,
            user_id=user_id,
            tool_id=tool_id,
            is_create=False,
        )

        file_system_path = (
            PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
                org_id=org_id,
                is_create=False,
                user_id=user_id,
                tool_id=str(tool_id),
            )
        )
        # TODO : Handle this with proper fix
        # Temporary Hack for frictionless onboarding as the user id will be empty
        if not fs_instance.exists(file_system_path):
            file_system_path = (
                PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
                    org_id=org_id,
                    is_create=True,
                    user_id="",
                    tool_id=str(tool_id),
                )
            )
        file_path = str(Path(file_system_path) / file_name)
        legacy_file_path = str(Path(legacy_file_system_path) / file_name)
        file_content_type = fs_instance.mime_type(file_path)
        if file_content_type == "application/pdf":
            # Read contents of PDF file into a string
            text_content_bytes: bytes = fs_instance.read(
                path=file_path,
                mode="rb",
                legacy_storage_path=legacy_file_path,
                encoding="utf-8",
            )
            encoded_string = base64.b64encode(bytes(text_content_bytes))
            return encoded_string

        elif file_content_type == "text/plain":
            text_content_string: str = fs_instance.read(
                path=file_path,
                mode="r",
                legacy_storage_path=legacy_file_path,
                encoding="utf-8",
            )
            return text_content_string
        else:
            raise ValueError(f"Unsupported file type: {file_content_type}")

    @staticmethod
    def delete_for_ide(org_id: str, user_id: str, tool_id: str, file_name: str) -> bool:
        """Method to delete file in remote while the corresponsing prompt
        studio project is deleted or the file is removed from the file manager.
        This method handles deleted for related files as well."""
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        file_system_path = (
            PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
                org_id=org_id,
                is_create=False,
                user_id=user_id,
                tool_id=str(tool_id),
            )
        )
        # Delete the source file
        fs_instance.rm(str(Path(file_system_path) / file_name))
        # Delete all related files for cascade delete
        directories = ["extract/", "extract/metadata/", "summarize/"]
        base_file_name, _ = os.path.splitext(file_name)
        # Delete related files
        file_paths = PromptStudioFileHelper._find_files(
            fs=fs_instance,
            base_file_name=base_file_name,
            base_path=file_system_path,
            directories=directories,
        )
        for file_path in file_paths:
            fs_instance.rm(file_path)
        return True

    @staticmethod
    def _find_files(
        fs: FileStorage, base_file_name: str, base_path: str, directories: list[str]
    ) -> list[str]:
        """This method is used to file files with the specific pattern
        determined using the list of directories passed and the base path.
        This is used to delete related(extract, metadata etc.) files generated
        for a specific prompt studio project."""
        file_paths = []
        pattern = f"{base_file_name}.*"
        for directory in directories:
            directory_path = str(Path(base_path) / directory)
            for file in fs.glob(f"{directory_path}/{pattern}"):
                file_paths.append(file)
        return file_paths
