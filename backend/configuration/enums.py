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
    min_value: Any = None
    max_value: Any = None


class ConfigKey(Enum):
    MAX_PARALLEL_FILE_BATCHES = ConfigSpec(
        default=settings.MAX_PARALLEL_FILE_BATCHES,
        value_type=ConfigType.INT,
        help_text="Maximum number of parallel file processing batches",
        min_value=1,
        max_value=settings.MAX_PARALLEL_FILE_BATCHES_MAX_VALUE,
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
            converted_value = converter(raw_value)
            return self._validate_value(converted_value)
        except Exception as e:
            raise ValueError(f"Failed to cast value '{raw_value}' to {value_type}: {e}")

    def _validate_value(self, value: Any) -> Any:
        """Validate the converted value against min/max constraints."""
        spec = self.value

        # Check min_value constraint
        if spec.min_value is not None and value < spec.min_value:
            raise ValueError(f"Value {value} is below minimum {spec.min_value}")

        # Check max_value constraint
        if spec.max_value is not None and value > spec.max_value:
            raise ValueError(f"Value {value} is above maximum {spec.max_value}")

        return value
