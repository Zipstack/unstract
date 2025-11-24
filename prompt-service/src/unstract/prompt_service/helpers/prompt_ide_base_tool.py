import os
import warnings

from flask import current_app

from unstract.prompt_service.constants import PromptServiceConstants
# Always use sdk1 for backward compatibility with existing prompt-studio code
from unstract.sdk1.constants import LogLevel
from unstract.sdk1.tool.stream import StreamMixin
from unstract.sdk1.utils.common import PY_TO_UNSTRACT_LOG_LEVEL


class PromptServiceBaseTool(StreamMixin):
    # Remove unused log_level arg
    def __init__(self, log_level: LogLevel | None = None, platform_key: str = "") -> None:
        """Args:
            tool (UnstractAbstractTool): Instance of UnstractAbstractTool.
                 Deprecated, will be removed in future versions
        Notes:
            - PLATFORM_SERVICE_API_KEY environment variable is required.
        """
        if log_level:
            warnings.warn(
                "The 'log_level' argument is deprecated and will be "
                "removed in a future version.",
                DeprecationWarning,
                stacklevel=2,  # ensures the warning points to the caller of the method
            )
        # Always use INFO for now to avoid log level validation issues
        effective_log_level = LogLevel.INFO
        self.platform_key = platform_key
        # Pass the LogLevel ENUM to StreamMixin
        # StreamMixin expects LogLevel enum, not string value
        super().__init__(log_level=effective_log_level)

    def get_env_or_die(self, env_key: str) -> str:
        """Returns the value of an env variable.

        If it is None, raises an error and exits

        Args:
            env_key (str): Key to retrieve

        Returns:
            str: Value of the env
        """
        # HACK: Adding platform key for multitenancy
        if env_key == PromptServiceConstants.PLATFORM_SERVICE_API_KEY:
            if not self.platform_key:
                current_app.logger.error(f"{env_key} is required")
            else:
                key: str = self.platform_key
                return key
        else:
            env_value = os.environ.get(env_key)
            if env_value is None:
                current_app.logger.error(f"Env variable {env_key} is required")
            return env_value  # type:ignore
        return ""
