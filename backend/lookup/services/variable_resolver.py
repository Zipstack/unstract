"""Variable resolver for template variable replacement."""

import json
import re
from typing import Any


class VariableResolver:
    """Resolves {{variable}} placeholders in prompt templates with actual values.

    Supports dot notation for nested field access and handles complex
    data types (dicts, lists) by converting them to JSON.
    """

    VARIABLE_PATTERN = r"\{\{([^}]*)\}\}"

    def __init__(self, input_data: dict[str, Any], reference_data: str):
        """Initialize the variable resolver with context data.

        Args:
            input_data: Extracted data from Prompt Studio
            reference_data: Concatenated text from all reference files
        """
        self.context = {"input_data": input_data, "reference_data": reference_data}

    def resolve(self, template: str) -> str:
        r"""Replace all {{variable}} references in template with actual values.

        Args:
            template: Prompt template with {{variable}} placeholders

        Returns:
            Resolved prompt with variables replaced

        Example:
            >>> resolver = VariableResolver(
            ...     {"vendor": "Slack Inc"}, "Slack\nMicrosoft\nGoogle"
            ... )
            >>> template = "Match {{input_data.vendor}} against: {{reference_data}}"
            >>> resolver.resolve(template)
            'Match Slack Inc against: Slack\nMicrosoft\nGoogle'
        """

        def replacer(match):
            variable_path = match.group(1).strip()
            return str(self._get_nested_value(variable_path))

        return re.sub(self.VARIABLE_PATTERN, replacer, template)

    def detect_variables(self, template: str) -> list[str]:
        """Extract all {{variable}} references from template.

        Args:
            template: Template text to analyze

        Returns:
            List of unique variable paths found in template

        Example:
            >>> resolver = VariableResolver({}, "")
            >>> template = "Match {{input_data.vendor}} from {{reference_data}} and {{input_data.vendor}}"
            >>> resolver.detect_variables(template)
            ['input_data.vendor', 'reference_data']
        """
        if not template:
            return []

        matches = re.findall(self.VARIABLE_PATTERN, template)
        # Strip whitespace and deduplicate
        unique_vars = list({m.strip() for m in matches})
        return sorted(unique_vars)

    def _get_nested_value(self, path: str) -> Any:
        """Get value from context using dot notation path.

        Args:
            path: Dot-separated path (e.g., "input_data.vendor.name")

        Returns:
            Value at path, or empty string if not found

        Examples:
            >>> resolver = VariableResolver({"vendor": {"name": "Slack"}}, "")
            >>> resolver._get_nested_value("input_data.vendor.name")
            'Slack'
            >>> resolver._get_nested_value("input_data.missing")
            ''
        """
        if not path:
            return ""

        keys = path.split(".")
        value = self.context

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, "")
            elif isinstance(value, list):
                # Try to convert key to integer for list indexing
                try:
                    index = int(key)
                    value = value[index] if 0 <= index < len(value) else ""
                except (ValueError, IndexError):
                    return ""
            else:
                return ""

        # If value is complex object, return JSON representation
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, ensure_ascii=False)

        # Handle None values
        if value is None:
            return ""

        return value

    def validate_variables(self, template: str) -> dict[str, bool]:
        """Validate that all variables in template can be resolved.

        Args:
            template: Template to validate

        Returns:
            Dictionary mapping variable paths to their availability status
        """
        variables = self.detect_variables(template)
        validation = {}

        for var in variables:
            value = self._get_nested_value(var)
            # Consider empty string as not available (could be missing)
            validation[var] = value != ""

        return validation

    def get_missing_variables(self, template: str) -> list[str]:
        """Get list of variables that cannot be resolved.

        Args:
            template: Template to check

        Returns:
            List of variable paths that resolve to empty/missing values
        """
        validation = self.validate_variables(template)
        return [var for var, available in validation.items() if not available]
