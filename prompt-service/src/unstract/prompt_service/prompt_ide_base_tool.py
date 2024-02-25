import os

from flask import current_app
from unstract.prompt_service.constants import LogLevel, PromptServiceContants
from unstract.sdk.tool.stream import StreamMixin


class PromptServiceBaseTool(StreamMixin):
    def __init__(
        self, log_level: LogLevel = LogLevel.INFO, platform_key: str = ""
    ) -> None:
        """
        Args:
            tool (UnstractAbstractTool): Instance of UnstractAbstractTool
        Notes:
            - PLATFORM_SERVICE_API_KEY environment variable is required.
        """
        self.log_level = log_level
        self.platform_key = platform_key
        super().__init__(log_level=log_level)

    def get_env_or_die(self, env_key: str) -> str:
        """Returns the value of an env variable.

        If its empty or None, raises an error and exits

        Args:
            env_key (str): Key to retrieve

        Returns:
            str: Value of the env
        """
        if env_key == PromptServiceContants.PLATFORM_SERVICE_API_KEY:
            if not self.platform_key:
                current_app.logger.error(f"{env_key} is required")
            else:
                key: str = self.platform_key
                return key
        else:
            env_value = os.environ.get(env_key)
            if env_value is None or env_value == "":
                current_app.logger.error(f"Env variable {env_key} is required")
            return env_value  # type:ignore
        return ""
