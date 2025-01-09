import os

from dotenv import load_dotenv
from unstract.runner.constants import Env
from unstract.runner.enum import LogLevel

load_dotenv()


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
