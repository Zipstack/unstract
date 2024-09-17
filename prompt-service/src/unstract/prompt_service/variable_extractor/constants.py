from enum import Enum


class VariableType(str, Enum):
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"


class VariableConstants:

    VARIABLE_REGEX = "{{(.+?)}}"
    DYNAMIC_VARIABLE_DATA_REGEX = r"\[(.*?)\]"
    DYNAMIC_VARIABLE_URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"  # noqa: E501
