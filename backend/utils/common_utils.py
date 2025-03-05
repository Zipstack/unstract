import json
from datetime import datetime
from enum import Enum

from django.utils import timezone


class CommonUtils:
    @staticmethod
    def str_to_bool(string: str) -> bool:
        """String value of boolean to boolean.

        Args:
            string (str): value like "true", "True" etc..

        Returns:
            bool
        """
        return string.lower() == "true"

    @staticmethod
    def is_json(string: str) -> bool:
        """Utility method to check if input is a JSON String.

        Args:
            string (str): String to be checked.

        Returns:
            bool : true if valid JSON String
        """
        try:
            json.loads(string)
        except json.JSONDecodeError:
            return False
        return True

    # TODO: Use from SDK
    @staticmethod
    def pretty_file_size(size_in_bytes: float):
        """Convert bytes to human-readable format (KB, MB, GB, etc.)."""
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_in_bytes)
        for unit in units:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    @staticmethod
    def time_since(start_time: datetime, precision: int = 3) -> float:
        """Compute the elapsed time given a starting time time in seconds

        Args:
            start_time (datetime): Time in seconds to compute from
            precision (int, optional): Floating point precision. Defaults to 3.

        Returns:
            float: Time elapsed since start_time
        """
        return round((timezone.now() - start_time).total_seconds(), precision)


class ModelEnum(Enum):
    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """Class method implementing model.TextChoice's choices() to enable
        using an enum in a model."""
        return [(key.value, key.name) for key in cls]
