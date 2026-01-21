"""JSON repair utility functions."""

from typing import Any

from json_repair import repair_json


def repair_json_with_best_structure(json_str: str) -> Any:
    """Intelligently repair JSON string using the best parsing strategy.

    This function attempts to parse JSON in two ways:
    1. As-is (could be valid object, array, or partial JSON)
    2. With array wrapping (useful for comma-separated objects)

    It chooses the result based on structural integrity rather than string length.

    Args:
        json_str: The JSON string to repair

    Returns:
        The parsed JSON object with the best structure
    """
    # Attempt parsing as-is
    parsed_as_is = repair_json(json_str=json_str, return_objects=True, ensure_ascii=False)

    # Attempt parsing with array wrap
    parsed_with_wrap = repair_json(
        json_str="[" + json_str, return_objects=True, ensure_ascii=False
    )

    # If both results are strings, return the as-is result
    if isinstance(parsed_as_is, str) and isinstance(parsed_with_wrap, str):
        return parsed_as_is

    # If only one is a string, return the non-string result
    if isinstance(parsed_as_is, str):
        return parsed_with_wrap
    if isinstance(parsed_with_wrap, str):
        return parsed_as_is

    # Both are valid structures - choose based on structure analysis
    # If parsed_with_wrap is a list with exactly one element that equals parsed_as_is,
    # then the original was already valid and wrapping just added unnecessary array
    if (
        isinstance(parsed_with_wrap, list)
        and len(parsed_with_wrap) == 1
        and parsed_with_wrap[0] == parsed_as_is
    ):
        return parsed_as_is

    # If parsed_as_is is a valid structure (dict or list), prefer it
    # unless parsed_with_wrap provides a more complete structure
    if isinstance(parsed_as_is, (dict, list)):
        # Check if the wrapped version provides multiple objects that were
        # incorrectly concatenated in the original (e.g., {},{},{})
        if isinstance(parsed_with_wrap, list) and len(parsed_with_wrap) > 1:
            # The original likely had multiple comma-separated objects
            return parsed_with_wrap
        else:
            # The original was already a valid structure
            return parsed_as_is

    # Default to wrapped version if we can't determine otherwise
    return parsed_with_wrap
