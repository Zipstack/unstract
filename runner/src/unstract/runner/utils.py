import logging
import os

from dotenv import load_dotenv

from unstract.runner.constants import Env
from unstract.runner.enum import LogLevel

load_dotenv()


logger = logging.getLogger(__name__)


class Utils:
    @staticmethod
    def str_to_bool(string: str) -> bool:
        """Convert string to boolean.

        Args:
            string (str): String to convert

        Returns:
            bool
        """
        if string.lower() == "true":
            return True
        elif string.lower() == "false":
            return False
        else:
            raise ValueError("Invalid boolean string")

    @staticmethod
    def str_to_int(value: str | None, default: int) -> int:
        """Safely convert a string to an integer, returning a default if conversion fails.

        Args:
            value (Optional[str]): The string to convert.
            default (int): The fallback value if conversion fails.

        Returns:
            int: Parsed integer or the default value.
        """
        if not value:
            return default

        try:
            return int(value)
        except ValueError:
            logger.warning(f"Invalid integer value '{value}'; using default: {default}")
            return default

    @staticmethod
    def get_log_level() -> LogLevel:
        """Get log level from environment variable.

        Returns:
            LogLevel
        """
        try:
            log_level_str = os.getenv(Env.LOG_LEVEL, "").upper()
            return LogLevel[log_level_str.upper()]
        except KeyError:
            return LogLevel.INFO

    @staticmethod
    def remove_container_on_exit() -> bool:
        """Get remove container on exit from environment variable.

        Returns:
            bool
        """
        return Utils.str_to_bool(os.getenv(Env.REMOVE_CONTAINER_ON_EXIT, "true"))

    @staticmethod
    def is_sidecar_enabled() -> bool:
        """Get sidecar enabled from environment variable.

        Returns:
            bool
        """
        if not Utils.str_to_bool(os.getenv(Env.TOOL_SIDECAR_ENABLED, "false")):
            return False

        image_name = os.getenv(Env.TOOL_SIDECAR_IMAGE_NAME)
        image_tag = os.getenv(Env.TOOL_SIDECAR_IMAGE_TAG)

        if not image_name or not image_tag:
            logger.warning(
                "Sidecar is enabled but configuration is incomplete: "
                f"image_name={'missing' if not image_name else 'set'}, "
                f"image_tag={'missing' if not image_tag else 'set'}"
            )
            return False
        return True

    @staticmethod
    def get_sidecar_wait_timeout() -> int:
        """Retrieve the timeout value from environment variables.

        Returns:
            int: Timeout in seconds, defaulting to 5 if not set or invalid.
        """
        raw_timeout = os.getenv(Env.TOOL_SIDECAR_CONTAINER_WAIT_TIMEOUT)
        return Utils.str_to_int(raw_timeout, default=5)
