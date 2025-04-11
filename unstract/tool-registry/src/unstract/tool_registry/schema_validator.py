import logging
from typing import Any

from jsonschema import exceptions, validate

from unstract.tool_registry.exceptions import InvalidSchemaInput

logger = logging.getLogger(__name__)


class JsonSchemaValidator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema

    def validate_data(self, data: dict[str, Any]) -> None:
        """Validates the input data against the schema
        Args:
            data (dict): The data to validate and filter.

        Returns:
            dict or None: The filtered data if valid,
                or None if there are validation errors.
        """
        try:
            validate(data, self.schema)
        except exceptions.ValidationError as e:
            logger.warning("Data is not valid against the schema")
            logger.error(f"Validation error: {e}")
            raise InvalidSchemaInput

    def validate_and_filter(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Validates the input data against the schema and filters the data
        based on the schema's properties.

        Args:
            data (dict): The data to validate and filter.

        Returns:
            dict or None: The filtered data if valid,
                or None if there are validation errors.
        """
        try:
            validate(data, self.schema)
            return self.filter_data(data)
        except exceptions.ValidationError as e:
            logger.warning("Data is not valid against the schema")
            logger.error(f"Validation error: {e}")
            return None

    def filter_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Filters the input data based on the schema's properties and returns
        the filtered data.

        Args:
            data (dict): The data to be filtered.

        Returns:
            dict: The filtered data.
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key in self.schema.get("properties", {}):
                result[key] = value
        return result
