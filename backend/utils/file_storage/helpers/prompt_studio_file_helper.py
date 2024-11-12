from typing import Any, Union

from file_management.exceptions import OrgIdNotValid
from utils.file_storage.common_utils import FileStorageUtil
from utils.file_storage.constants import FileStorageConstants, FileStorageType
from utils.file_storage.helpers.common_file_helper import FileStorageHelper

from unstract.connectors.filesystems.local_storage.local_storage import LocalStorageFS


class PromptStudioFileHelper:
    @staticmethod
    def handle_sub_directory_for_prompt_studio(
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
        base_path = FileStorageUtil.get_env_or_die(
            env_key=FileStorageConstants.PROMPT_STUDIO_FILE_PATH
        )
        file_path = f"{base_path}/{org_id}/{user_id}/{tool_id}"
        extract_file_path = f"{file_path}/extract"
        summarize_file_path = f"{file_path}/summarize"
        if is_create:
            fs_instance = FileStorageHelper.initialize_file_storage(
                type=FileStorageType.PERMANENT
            )
            fs_instance.mkdir(file_path, create_parents=True)
            fs_instance.mkdir(extract_file_path, create_parents=True)
            fs_instance.mkdir(summarize_file_path, create_parents=True)
        return str(file_path)

    @staticmethod
    def upload_for_ide(
        org_id: str, user_id: str, tool_id: str, uploaded_file: Any
    ) -> None:
        fs_instance = FileStorageHelper.initialize_file_storage(
            type=FileStorageType.PERMANENT
        )
        file_system_path = (
            PromptStudioFileHelper.handle_sub_directory_for_prompt_studio(
                org_id=org_id,
                is_create=True,
                user_id=user_id,
                tool_id=str(tool_id),
            )
        )

        file_path = f"{file_system_path}/{uploaded_file.name}"
        fs_instance.write(path=file_path, mode="wb", data=uploaded_file.read())

    @staticmethod
    def upload_file(
        org_id: str, user_id: str, tool_id: str, uploaded_file: Any
    ) -> None:
        # file_system = FileStorageHelper.initialize_file_storage(
        #     type=FileStorageType.PERMANENT
        # )

        file_system_path = (
            PromptStudioFileHelper.handle_sub_directory_for_prompt_studio(
                org_id=org_id,
                is_create=True,
                user_id=user_id,
                tool_id=str(tool_id),
            )
        )
        print("***** file_system_path ***** ", file_system_path)

        file_system = LocalStorageFS(settings={"path": file_system_path})
        fs = file_system.get_fsspec_fs()

        file_path = f"{file_system_path}/{uploaded_file.name}"
        # file_system.write(path=file_path, mode="wb", data=uploaded_file.read())
        with fs.open(file_path, mode="wb") as remote_file:
            print("***** uploaded_file ***** ", uploaded_file)
            print("***** remote_file ***** ", remote_file)
            remote_file.write(uploaded_file.read())

    @staticmethod
    def fetch_file_contents(
        org_id: str, user_id: str, tool_id: str, file_name: str
    ) -> Union[bytes, str]:
        fs_instance = FileStorageHelper.initialize_file_storage(
            type=FileStorageType.PERMANENT
        )
        file_system_path = (
            PromptStudioFileHelper.handle_sub_directory_for_prompt_studio(
                org_id=org_id,
                is_create=True,
                user_id=user_id,
                tool_id=str(tool_id),
            )
        )
        # TODO : Handle this with proper fix
        # Temporary Hack for frictionless onboarding as the user id will be empty
        if not fs_instance.exists(file_system_path):
            file_system_path = (
                PromptStudioFileHelper.handle_sub_directory_for_prompt_studio(
                    org_id=org_id,
                    is_create=True,
                    user_id="",
                    tool_id=str(tool_id),
                )
            )
        file_path = f"{file_system_path}/{file_name}"
        file_content_type = fs_instance.mime_type(file_path)
        text_content: Union[bytes, str]
        if file_content_type == "application/pdf":
            # Read contents of PDF file into a string
            text_content = fs_instance.read(path=file_path, mode="rb")

        elif file_content_type == "text/plain":
            text_content = fs_instance.read(path=file_path, mode="r")

        return text_content
