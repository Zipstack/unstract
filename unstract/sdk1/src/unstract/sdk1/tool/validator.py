import re
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError, validators
from unstract.sdk.constants import MetadataKey, PropKey
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.mime_types import EXT_MIME_MAP
from unstract.sdk.utils import Utils


def extend_with_default(validator_class: Any) -> Any:
    """Extend a JSON schema validator class with a default value functionality.

    Parameters:
    - validator_class (Any): The JSON schema validator class to be extended.

    Returns:
    - Any: The extended JSON schema validator class.

    Example:
    extend_with_default(Draft202012Validator)
    """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator: Any, properties: Any, instance: Any, schema: Any) -> Any:
        for property_, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property_, subschema["default"])

        yield from validate_properties(
            validator,
            properties,
            instance,
            schema,
        )

    return validators.extend(
        validator_class,
        {"properties": set_defaults},
    )


# Helps validate a JSON against a schema and applies missing key's defaults too.
DefaultsGeneratingValidator = extend_with_default(Draft202012Validator)


class ToolValidator:
    """Class to validate a tool and its configuration before its executed with
    an input."""

    def __init__(self, tool: BaseTool) -> None:
        self.tool = tool
        props = self.tool.properties
        self.restrictions = props.get(PropKey.RESTRICTIONS)

    def validate_pre_execution(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Performs validation before the tool executes on the input file.

        Args:
            settings (dict[str, Any]): Settings configured for the tool

        Returns:
            dict[str, Any]: Settings JSON for a tool (filled with defaults)
        """
        input_file = Path(self.tool.get_input_file())
        file_exists = self.tool.workflow_filestorage.exists(path=input_file)

        if not file_exists:
            self.tool.stream_error_and_exit(f"Input file not found: {input_file}")
        self._validate_restrictions(input_file)
        self._validate_settings_and_fill_defaults(settings)
        # Call tool's validation hook to execute custom validation
        self.tool.validate(str(input_file), settings)
        return settings

    def _validate_restrictions(self, input_file: Path) -> None:
        """Validates the restrictions mentioned in the tool's PROPERTIES.

        Args:
            input_file (Path): Path object to the input file to be validated
        """
        self._validate_file_size(input_file)
        self._validate_file_type(input_file)

    def _validate_settings_and_fill_defaults(self, tool_settings: dict[str, Any]) -> None:
        """Validates and obtains settings for a tool.

        Validation is done against the tool's settings based
        on its declared SPEC. Validator also fills in the missing defaults.

        Args:
            tool_settings (dict[str, Any]): Tool settings to validate
        """
        try:
            spec_schema = self.tool.spec
            DefaultsGeneratingValidator(spec_schema).validate(tool_settings)
        except JSONDecodeError as e:
            self.tool.stream_error_and_exit(f"Settings is not a valid JSON: {str(e)}")
        except ValidationError as e:
            self.tool.stream_error_and_exit(f"Invalid settings: {str(e)}")

    def _validate_file_size(self, input_file: Path) -> None:
        """Validates the input file size against the max allowed size set in
        the tool's PROPERTIES.

        Raises:
            RuntimeError: File size exceeds max allowed size
        """
        max_file_size = self.restrictions.get(PropKey.MAX_FILE_SIZE)
        max_size_in_bytes = self._parse_size_string(max_file_size)

        self.tool.stream_log(
            f"Checking input file size... (max file size: {max_file_size})"
        )
        file_size = self.tool.workflow_filestorage.size(path=input_file)
        self.tool.stream_log(f"Input file size: {Utils.pretty_file_size(file_size)}")

        if file_size > max_size_in_bytes:
            source_name = self.tool.get_exec_metadata.get(MetadataKey.SOURCE_NAME)
            self.tool.stream_error_and_exit(
                f"File {source_name} exceeds the maximum "
                f"allowed size of {max_file_size}"
            )

    def _parse_size_string(self, size_string: str) -> int:
        """Parses the size string for validation.

        Args:
            size_string (str): Size string to be parsed

        Raises:
            ValueError: Invalid size format

        Returns:
            int: Size in bytes
        """
        size_match = re.match(PropKey.FILE_SIZE_REGEX, size_string)
        if not size_match:
            self.tool.stream_error_and_exit(f"Invalid size string format: {size_string}")

        size, unit = size_match.groups()
        size_in_bytes = int(size)
        if unit.upper() == "KB":
            size_in_bytes *= 1024
        elif unit.upper() == "MB":
            size_in_bytes *= 1024 * 1024
        elif unit.upper() == "GB":
            size_in_bytes *= 1024 * 1024 * 1024
        elif unit.upper() == "TB":
            size_in_bytes *= 1024 * 1024 * 1024 * 1024

        return size_in_bytes

    def _validate_file_type(self, input_file: Path) -> None:
        """Validate the input file type against the allowed types mentioned in
        tool's PROPERTIES.

        Args:
            input_file (Path): Path obj of input file to validate

        Raises:
            RuntimeError: If file type is not supported by the tool
        """
        self.tool.stream_log("Checking input file type...")

        allowed_exts: list[str] = self.restrictions.get(PropKey.ALLOWED_FILE_TYPES)
        allowed_exts = [allowed_type.lower() for allowed_type in allowed_exts]
        if "*" in allowed_exts:
            self.tool.stream_log("Skipping check, tool allows all file types")
            return

        allowed_mimes = []
        for ext in allowed_exts:
            if ext not in EXT_MIME_MAP:
                self.tool.stream_error_and_exit(
                    f"{ext} mentioned in tool PROPERTIES is not supported"
                )
            allowed_mimes.append(EXT_MIME_MAP[ext])
        tool_fs = self.tool.workflow_filestorage
        input_file_mime = tool_fs.mime_type(input_file)
        self.tool.stream_log(f"Input file MIME: {input_file_mime}")
        if input_file_mime not in allowed_mimes:
            self.tool.stream_error_and_exit(
                f"File type of {input_file_mime} is not supported by"
                " the tool, check its PROPERTIES for a list of supported types"
            )
