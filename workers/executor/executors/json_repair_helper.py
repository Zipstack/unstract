"""JSON repair utility functions.

Copied from prompt-service/.../utils/json_repair_helper.py — already Flask-free.
"""

import json
from typing import Any


def repair_json_with_best_structure(json_str: str) -> Any:
    """Intelligently repair JSON string using the best parsing strategy.

    Attempts to parse as valid JSON first, then falls back to basic repair
    heuristics. The full ``json_repair`` library is used when available for
    more aggressive repair.

    Args:
        json_str: The JSON string to repair

    Returns:
        The parsed JSON object with the best structure
    """
    # Fast path — try strict JSON first
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to import json_repair for advanced repair
    try:
        from json_repair import repair_json

        parsed_as_is = repair_json(
            json_str=json_str, return_objects=True, ensure_ascii=False
        )
        parsed_with_wrap = repair_json(
            json_str="[" + json_str, return_objects=True, ensure_ascii=False
        )

        if isinstance(parsed_as_is, str) and isinstance(parsed_with_wrap, str):
            return parsed_as_is
        if isinstance(parsed_as_is, str):
            return parsed_with_wrap
        if isinstance(parsed_with_wrap, str):
            return parsed_as_is

        if (
            isinstance(parsed_with_wrap, list)
            and len(parsed_with_wrap) == 1
            and parsed_with_wrap[0] == parsed_as_is
        ):
            return parsed_as_is

        if isinstance(parsed_as_is, (dict, list)):
            if isinstance(parsed_with_wrap, list) and len(parsed_with_wrap) > 1:
                return parsed_with_wrap
            else:
                return parsed_as_is

        return parsed_with_wrap
    except ImportError:
        # json_repair not installed — return the raw string
        return json_str
