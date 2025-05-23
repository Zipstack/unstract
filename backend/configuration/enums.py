import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from django.conf import settings


class ConfigType(Enum):
    INT = "int"
    STRING = "string"
    BOOL = "bool"
    JSON = "json"


@dataclass(frozen=True)
class ConfigSpec:
    default: Any
    value_type: ConfigType
    help_text: str


class ConfigKey(Enum):
    MAX_PARALLEL_FILE_BATCHES = ConfigSpec(
        default=settings.MAX_PARALLEL_FILE_BATCHES,
        value_type=ConfigType.INT,
        help_text="Maximum number of parallel file processing batches",
    )

    def cast_value(self, raw_value: Any):
        converters = {
            ConfigType.INT: int,
            ConfigType.BOOL: lambda v: v.lower() in ("true", "1"),
            ConfigType.JSON: json.loads,
            ConfigType.STRING: str,
        }
        value_type = self.value.value_type
        converter = converters.get(value_type)
        try:
            return converter(raw_value)
        except Exception as e:
            raise ValueError(f"Failed to cast value '{raw_value}' to {value_type}: {e}")
