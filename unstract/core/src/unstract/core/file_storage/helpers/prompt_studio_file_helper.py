from file_management.exceptions import OrgIdNotValid
from unstract.core.file_storage.common_utils import FileStorageUtil
from unstract.core.file_storage.constants import FileStorageConstants
from unstract.core.file_storage.helpers.common_file_helper import FileStorageHelper
from unstract.core.file_storage.constants import FileStorageType

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
        base_path = FileStorageUtil.get_env_or_die(env_key=FileStorageConstants.PROMPT_STUDIO_FILE_PATH)
        file_path = f"{base_path}/{org_id}/{user_id}/{tool_id}"
        extract_file_path = f"{file_path}/extract"
        summarize_file_path = f"{file_path}/summarize"
        if is_create:
            fs_instance = FileStorageHelper.initialize_file_storage(type=FileStorageType.PERMANENT)
            fs_instance.mkdir(file_path, create_parents=True)
            fs_instance.mkdir(extract_file_path, create_parents=True)
            fs_instance.mkdir(summarize_file_path, create_parents=True)
        return str(file_path)
