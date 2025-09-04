"""Conversion Utilities for Dataclass Migration

Utility functions to handle conversion between dictionaries and dataclasses
during the migration process. These utilities help maintain backward compatibility
while gradually moving to type-safe dataclass patterns.
"""

import os
import sys
from dataclasses import is_dataclass
from typing import Any, TypeVar

# Import shared domain models from core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core import serialize_dataclass_to_dict

from .api_responses import (
    BaseAPIResponse,
    FileExecutionResponse,
    WorkflowExecutionResponse,
)

# Import our dataclasses
from .execution_models import (
    WorkflowConfig,
    WorkflowContextData,
)
from .notification_models import (
    NotificationRequest,
    WebhookNotificationRequest,
)
from .result_models import (
    WorkflowExecutionResult,
)

T = TypeVar("T")


class ConversionError(Exception):
    """Exception raised when conversion between dict and dataclass fails."""

    pass


def ensure_dataclass(data: dict[str, Any] | T, target_class: type[T]) -> T:
    """Ensure data is converted to target dataclass if it's a dictionary.

    Args:
        data: Either a dictionary or an instance of target_class
        target_class: The dataclass type to convert to

    Returns:
        Instance of target_class

    Raises:
        ConversionError: If conversion fails
    """
    if isinstance(data, target_class):
        return data

    if isinstance(data, dict):
        try:
            if hasattr(target_class, "from_dict"):
                return target_class.from_dict(data)
            else:
                # Try direct instantiation with dict unpacking
                return target_class(**data)
        except Exception as e:
            raise ConversionError(
                f"Failed to convert dict to {target_class.__name__}: {str(e)}"
            ) from e

    raise ConversionError(
        f"Cannot convert {type(data)} to {target_class.__name__}. "
        f"Expected dict or {target_class.__name__} instance."
    )


def ensure_dict(data: dict[str, Any] | Any) -> dict[str, Any]:
    """Ensure data is converted to dictionary if it's a dataclass.

    Args:
        data: Either a dictionary or a dataclass instance

    Returns:
        Dictionary representation of the data

    Raises:
        ConversionError: If conversion fails
    """
    if isinstance(data, dict):
        return data

    if is_dataclass(data):
        try:
            if hasattr(data, "to_dict"):
                return data.to_dict()
            else:
                return serialize_dataclass_to_dict(data)
        except Exception as e:
            raise ConversionError(
                f"Failed to convert {type(data).__name__} to dict: {str(e)}"
            ) from e

    # For other types, try to convert to dict if possible
    if hasattr(data, "__dict__"):
        return data.__dict__

    raise ConversionError(
        f"Cannot convert {type(data)} to dict. Expected dict or dataclass instance."
    )


def convert_workflow_config(config: dict[str, Any] | WorkflowConfig) -> WorkflowConfig:
    """Convert workflow configuration to WorkflowConfig dataclass.

    Args:
        config: Dictionary or WorkflowConfig instance

    Returns:
        WorkflowConfig dataclass instance
    """
    return ensure_dataclass(config, WorkflowConfig)


def convert_execution_context(
    context: dict[str, Any] | WorkflowContextData,
) -> WorkflowContextData:
    """Convert execution context to WorkflowContextData dataclass.

    Args:
        context: Dictionary or WorkflowContextData instance

    Returns:
        WorkflowContextData dataclass instance
    """
    return ensure_dataclass(context, WorkflowContextData)


def convert_notification_request(
    request: dict[str, Any] | NotificationRequest | WebhookNotificationRequest,
) -> NotificationRequest | WebhookNotificationRequest:
    """Convert notification request to appropriate dataclass.

    Args:
        request: Dictionary, NotificationRequest, or WebhookNotificationRequest

    Returns:
        Appropriate notification request dataclass
    """
    if isinstance(request, (NotificationRequest, WebhookNotificationRequest)):
        return request

    if isinstance(request, dict):
        # Determine the appropriate dataclass based on the data
        notification_type = request.get("notification_type", "WEBHOOK")

        if notification_type == "WEBHOOK" or "url" in request:
            return ensure_dataclass(request, WebhookNotificationRequest)
        else:
            return ensure_dataclass(request, NotificationRequest)

    raise ConversionError(
        f"Cannot convert {type(request)} to notification request dataclass"
    )


def convert_execution_result(
    result: dict[str, Any] | WorkflowExecutionResult,
) -> WorkflowExecutionResult:
    """Convert execution result to WorkflowExecutionResult dataclass.

    Args:
        result: Dictionary or WorkflowExecutionResult instance

    Returns:
        WorkflowExecutionResult dataclass instance
    """
    return ensure_dataclass(result, WorkflowExecutionResult)


def batch_convert_to_dataclass(
    items: list[dict[str, Any] | T], target_class: type[T]
) -> list[T]:
    """Convert a list of dictionaries/dataclasses to target dataclass type.

    Args:
        items: List of dictionaries or dataclass instances
        target_class: The dataclass type to convert to

    Returns:
        List of target_class instances

    Raises:
        ConversionError: If any conversion fails
    """
    converted = []
    for i, item in enumerate(items):
        try:
            converted.append(ensure_dataclass(item, target_class))
        except ConversionError as e:
            raise ConversionError(f"Failed to convert item {i}: {str(e)}") from e

    return converted


def batch_convert_to_dict(items: list[dict[str, Any] | Any]) -> list[dict[str, Any]]:
    """Convert a list of dataclasses/dictionaries to dictionaries.

    Args:
        items: List of dataclass instances or dictionaries

    Returns:
        List of dictionaries

    Raises:
        ConversionError: If any conversion fails
    """
    converted = []
    for i, item in enumerate(items):
        try:
            converted.append(ensure_dict(item))
        except ConversionError as e:
            raise ConversionError(f"Failed to convert item {i}: {str(e)}") from e

    return converted


def safe_convert_to_dataclass(
    data: dict[str, Any] | T, target_class: type[T], default: T | None = None
) -> T | None:
    """Safely convert data to dataclass, returning default on failure.

    Args:
        data: Data to convert
        target_class: Target dataclass type
        default: Default value to return on conversion failure

    Returns:
        Converted dataclass instance or default value
    """
    try:
        return ensure_dataclass(data, target_class)
    except ConversionError:
        return default


def safe_convert_to_dict(
    data: dict[str, Any] | Any, default: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Safely convert data to dictionary, returning default on failure.

    Args:
        data: Data to convert
        default: Default value to return on conversion failure

    Returns:
        Converted dictionary or default value
    """
    try:
        return ensure_dict(data)
    except ConversionError:
        return default or {}


def create_backward_compatible_function(original_func, conversion_mapping):
    """Create a backward compatible version of a function with automatic conversion.

    This decorator can be used to wrap functions that have been updated to use
    dataclasses but need to maintain backward compatibility with dictionary inputs.

    Args:
        original_func: The function to wrap
        conversion_mapping: Dict mapping parameter names to conversion functions

    Returns:
        Wrapped function that automatically converts parameters
    """

    def wrapper(*args, **kwargs):
        # Convert positional arguments if needed
        converted_args = list(args)

        # Convert keyword arguments if needed
        converted_kwargs = {}
        for key, value in kwargs.items():
            if key in conversion_mapping:
                converter = conversion_mapping[key]
                try:
                    converted_kwargs[key] = converter(value)
                except ConversionError:
                    # Keep original value if conversion fails
                    converted_kwargs[key] = value
            else:
                converted_kwargs[key] = value

        return original_func(*converted_args, **converted_kwargs)

    return wrapper


# Pre-configured conversion functions for common use cases
def convert_workflow_execution_data(
    data: dict[str, Any] | WorkflowContextData,
) -> WorkflowContextData:
    """Convert workflow execution data with enhanced error handling."""
    if isinstance(data, WorkflowContextData):
        return data

    if not isinstance(data, dict):
        raise ConversionError(f"Expected dict or WorkflowContextData, got {type(data)}")

    # Ensure required fields are present
    required_fields = ["workflow_id", "workflow_name", "workflow_type", "execution_id"]
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        raise ConversionError(f"Missing required fields: {missing_fields}")

    return WorkflowContextData.from_dict(data)


def convert_api_response_data(data: dict[str, Any] | BaseAPIResponse) -> BaseAPIResponse:
    """Convert API response data with type detection."""
    if isinstance(data, BaseAPIResponse):
        return data

    if not isinstance(data, dict):
        raise ConversionError(f"Expected dict or BaseAPIResponse, got {type(data)}")

    # Try to determine the specific response type based on data content
    if "workflow_id" in data:
        return WorkflowExecutionResponse.from_api_response(data)
    elif "file_execution_id" in data:
        return FileExecutionResponse.from_api_response(data)
    else:
        return BaseAPIResponse.from_api_response(data)


# Utility constants for common conversion patterns
def _workflow_config_converter(x):
    return convert_workflow_config(x)


def _execution_context_converter(x):
    return convert_execution_context(x)


def _notification_request_converter(x):
    return convert_notification_request(x)


def _execution_result_converter(x):
    return convert_execution_result(x)


WORKFLOW_CONFIG_CONVERTER = _workflow_config_converter
EXECUTION_CONTEXT_CONVERTER = _execution_context_converter
NOTIFICATION_REQUEST_CONVERTER = _notification_request_converter
EXECUTION_RESULT_CONVERTER = _execution_result_converter
