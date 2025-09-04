"""Cache Utilities

Common utility functions for cache operations.
"""

import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


def make_json_serializable(obj: Any) -> Any:
    """Convert an object to JSON-serializable format.

    Handles common non-serializable types like dataclasses, enums, and datetime objects.
    This is the single source of truth for JSON serialization in the cache system.

    Args:
        obj: Object to serialize

    Returns:
        JSON-serializable version of the object with type information for reconstruction
    """

    def serialize_item(item):
        if item is None:
            return None
        elif isinstance(item, (str, int, float, bool)):
            return item
        elif isinstance(item, (list, tuple)):
            return [serialize_item(i) for i in item]
        elif isinstance(item, dict):
            return {k: serialize_item(v) for k, v in item.items()}
        elif isinstance(item, Enum):
            return item.value
        elif isinstance(item, datetime):
            return item.isoformat()
        elif is_dataclass(item):
            # Store type information for reconstruction
            serialized = serialize_item(asdict(item))
            return {
                "__type__": f"{item.__class__.__module__}.{item.__class__.__name__}",
                "__data__": serialized,
            }
        elif hasattr(item, "__dict__"):
            # Handle objects with __dict__ (like API response objects)
            serialized = serialize_item(item.__dict__)
            return {
                "__type__": f"{item.__class__.__module__}.{item.__class__.__name__}",
                "__data__": serialized,
            }
        else:
            # Fallback - convert to string
            return str(item)

    try:
        return serialize_item(obj)
    except Exception as e:
        logger.warning(f"Failed to serialize object for caching: {e}")
        # Return a simple representation that can be cached
        return {"error": "serialization_failed", "type": str(type(obj))}


def reconstruct_from_cache(cached_data: Any) -> Any:
    """Reconstruct objects from cached data using type information.

    Args:
        cached_data: Data retrieved from cache

    Returns:
        Reconstructed object or original data if no type info
    """

    def reconstruct_item(item):
        if item is None:
            return None
        elif isinstance(item, (str, int, float, bool)):
            return item
        elif isinstance(item, list):
            return [reconstruct_item(i) for i in item]
        elif isinstance(item, dict):
            # Check if this is a typed object
            if "__type__" in item and "__data__" in item:
                return reconstruct_typed_object(item["__type__"], item["__data__"])
            else:
                return {k: reconstruct_item(v) for k, v in item.items()}
        else:
            return item

    try:
        return reconstruct_item(cached_data)
    except Exception as e:
        logger.warning(f"Failed to reconstruct object from cache: {e}")
        return cached_data


def reconstruct_typed_object(type_name: str, data: Any) -> Any:
    """Reconstruct a typed object from cached data.

    Args:
        type_name: Full type name (module.ClassName)
        data: Serialized object data

    Returns:
        Reconstructed object or original data if reconstruction fails
    """
    try:
        # Registry of reconstructable types - cleaner than hardcoded strings
        type_registry = _get_type_registry()

        # Extract class name from full type path
        class_name = type_name.split(".")[-1]

        # Find matching class in registry
        if class_name in type_registry:
            cls = type_registry[class_name]
            return cls(**data)
        else:
            logger.debug(f"Unknown type for reconstruction: {type_name}")
            return data

    except Exception as e:
        logger.warning(f"Failed to reconstruct {type_name}: {e}")
        return data


def _get_type_registry() -> dict[str, type]:
    """Get registry of reconstructable types.

    Returns:
        Dictionary mapping class names to classes
    """
    try:
        from ..models.api_responses import (
            FileBatchResponse,
            FileExecutionResponse,
            FileHistoryResponse,
            ManualReviewResponse,
            ToolExecutionResponse,
            ToolInstancesResponse,
            WorkflowDefinitionResponse,
            WorkflowEndpointsResponse,
            WorkflowExecutionResponse,
        )

        return {
            "WorkflowEndpointsResponse": WorkflowEndpointsResponse,
            "ToolInstancesResponse": ToolInstancesResponse,
            "WorkflowDefinitionResponse": WorkflowDefinitionResponse,
            "WorkflowExecutionResponse": WorkflowExecutionResponse,
            "FileExecutionResponse": FileExecutionResponse,
            "ManualReviewResponse": ManualReviewResponse,
            "FileBatchResponse": FileBatchResponse,
            "ToolExecutionResponse": ToolExecutionResponse,
            "FileHistoryResponse": FileHistoryResponse,
        }
    except ImportError as e:
        logger.warning(f"Failed to import response types for cache reconstruction: {e}")
        return {}
