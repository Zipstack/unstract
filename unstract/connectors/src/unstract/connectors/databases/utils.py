"""Database Utilities

Common utilities for database connectors to ensure consistent data handling
across all database types (BigQuery, PostgreSQL, MySQL, Snowflake, etc.).
"""

import math
from typing import Any


def sanitize_floats_for_database(data: Any) -> Any:
    """Sanitize special float values (NaN, Inf) for database compatibility.

    This minimal sanitization applies to all databases. It only handles
    special float values that no database can store in JSON:
    - NaN (Not a Number) → None
    - Infinity → None
    - -Infinity → None

    Database-specific precision handling (like BigQuery's round-trip requirements)
    should be implemented in the respective database connector.

    Args:
        data: The data structure to sanitize (dict, list, or primitive)

    Returns:
        Sanitized data with NaN/Inf converted to None

    Example:
        >>> sanitize_floats_for_database({"value": float("nan")})
        {'value': None}

        >>> sanitize_floats_for_database({"value": float("inf")})
        {'value': None}

        >>> sanitize_floats_for_database({"price": 1760509016.282637})
        {'price': 1760509016.282637}  # Unchanged - precision preserved
    """
    if isinstance(data, float):
        # Only handle special values that no database supports
        if math.isnan(data) or math.isinf(data):
            return None
        # Return unchanged - let database connector handle precision if needed
        return data
    elif isinstance(data, dict):
        return {k: sanitize_floats_for_database(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_floats_for_database(item) for item in data]
    else:
        # Return other types unchanged (int, str, bool, None, etc.)
        return data
