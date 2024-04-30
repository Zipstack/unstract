import os

from dotenv import load_dotenv
from unstract.worker.enum import LogLevel
from unstract.worker.constants import Env

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
            log_level_str = os.environ.get(Env.LOG_LEVEL, "").upper()
            return LogLevel[log_level_str.upper()]
        except KeyError:
            return LogLevel.INFO

    @staticmethod
    def remove_container_on_exit() -> bool:
        """Get remove container on exit from environment variable.

        Returns:
            bool
        """
        return Utils.str_to_bool(os.environ.get(Env.REMOVE_CONTAINER_ON_EXIT, "true"))
