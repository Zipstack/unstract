import json
from enum import Enum


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
    def pretty_file_size(num: float, suffix: str = "B") -> str:
        """Gets the human readable size for a file,

        Args:
            num (int): Size in bytes to parse
            suffix (str, optional): _description_. Defaults to "B".

        Returns:
            str: Human readable size
        """
        for unit in ("", "K", "M", "G", "T"):
            if abs(num) < 1024.0:
                # return f"{num:3.1f} {unit}{suffix}"
                return f"{num:.2f} {unit}{suffix}"
            num /= 1024.0
        return f"{num:.2f} {suffix}"


class ModelEnum(Enum):
    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """Class method implementing model.TextChoice's choices() to enable
        using an enum in a model."""
        return [(key.value, key.name) for key in cls]
