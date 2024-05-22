import uuid
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


class ModelEnum(Enum):
    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """Class method implementing model.TextChoice's choices() to enable
        using an enum in a model."""
        return [(key.value, key.name) for key in cls]

    @classmethod
    def get_uuid(cls) -> str:
        """Class method to get uuid."""
        return str(uuid.uuid4())
