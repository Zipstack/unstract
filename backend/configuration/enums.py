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
    """Enum defining available configuration keys for organization-level overrides.

    This enum serves as the central registry for all configurable system settings
    that can be overridden on a per-organization basis. Each enum value contains
    a ConfigSpec that defines:

    - default: The default value (usually from Django settings)
    - value_type: The expected data type (INT, STRING, BOOL, JSON)
    - help_text: Human-readable description of the setting
    - min_value/max_value: Optional validation constraints

    Usage:
        # Get organization-specific config value
        batch_size = Configuration.get_value_by_organization(
            config_key=ConfigKey.MAX_PARALLEL_FILE_BATCHES,
            organization=organization
        )

        # The method automatically handles:
        # - Fallback to default if no override exists
        # - Type conversion and validation
        # - Min/max constraint checking
        # - Error handling with safe defaults

    Adding New Configuration Keys:
        1. Add a new enum value with appropriate ConfigSpec
        2. No database migration required - validation is application-level
        3. Organizations can immediately override the new setting
    """

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
            ConfigType.BOOL: lambda v: v.lower() in ("true", "1")
            if isinstance(v, str)
            else bool(v),
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
