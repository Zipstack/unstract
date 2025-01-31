import os

from platform_settings_v2.platform_auth_service import PlatformAuthenticationService
from prompt_studio.prompt_studio_core_v2.constants import ToolStudioKeys
from unstract.sdk.constants import LogLevel
from unstract.sdk.tool.stream import StreamMixin


class PromptIdeBaseTool(StreamMixin):
    def __init__(self, log_level: LogLevel = LogLevel.INFO, org_id: str = "") -> None:
        """
        Args:
            tool (UnstractAbstractTool): Instance of UnstractAbstractTool
        Notes:
            - PLATFORM_SERVICE_API_KEY environment variable is required.
        """
        self.log_level = log_level
        self.org_id = org_id
        self.workflow_filestorage = None

        super().__init__(log_level=log_level)

    def get_env_or_die(self, env_key: str) -> str:
        """Returns the value of an env variable.

        If its empty or None, raises an error and exits

        Args:
            env_key (str): Key to retrieve

        Returns:
            str: Value of the env
        """
        # HACK: Adding platform key for multitenancy
        if env_key == ToolStudioKeys.PLATFORM_SERVICE_API_KEY:
            platform_key = PlatformAuthenticationService.get_active_platform_key(
                self.org_id
            )
            key: str = str(platform_key.key)
            return key
        else:
            env_value = os.environ.get(env_key)
            if env_value is None or env_value == "":
                self.stream_error_and_exit(f"Env variable {env_key} is required")
            return env_value  # type:ignore
