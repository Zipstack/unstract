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


class ModelEnum(Enum):
    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """Class method implementing model.TextChoice's choices() to enable
        using an enum in a model."""
        return [(key.value, key.name) for key in cls]
