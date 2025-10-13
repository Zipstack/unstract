from typing import Any

from json_repair import repair_json


def json_to_markdown(data: Any, level: int = 0, parent_key: str = "") -> str:
    markdown = ""
    indent = "  " * level  # Increase indentation by 2 for nested levels

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                # If value is a dict or list, make it expandable
                markdown += f"{indent}- **{key}**:\n"
                markdown += json_to_markdown(value, level + 1, key)
            else:
                markdown += f"{indent}- **{key}**: {value}\n"
    elif isinstance(data, list):
        for index, item in enumerate(data, 1):
            # Use parent key for list item naming
            # Fall back to "Item" if parent_key is empty
            # TODO: Determine child key using parent key for all plural combinations
            item_label = (
                f"{parent_key[:-1] if parent_key.endswith('s') else parent_key} {index}"
                if parent_key
                else f"Item {index}"
            )
            markdown += f"{indent}- **{item_label}**\n"
            markdown += json_to_markdown(item, level + 1, parent_key)
    else:
        markdown += f"{indent}- {data}\n"

    return markdown


def repair_json_with_best_structure(json_str: str) -> Any:
    """Repair and parse a potentially malformed JSON string with optimal structure detection.

    This function attempts to repair and parse a JSON string using two different strategies
    and returns the result that produces the most useful data structure. It handles cases
    where the input might be incomplete, malformed, or ambiguous JSON.

    The function tries two parsing approaches:
    1. Parse the JSON string as-is
    2. Parse the JSON string wrapped in array brackets [...]

    It then intelligently selects the best result based on the following logic:
    - If both results are strings (failed to parse as objects), return the as-is result
    - If one result is a string and the other is an object/array, return the object/array
    - If wrapping produces a single-element list that equals the as-is result, return as-is
    - If as-is produces an object/array and wrapping produces multiple elements, prefer wrapped
    - Otherwise, prefer the as-is result

    Args:
        json_str: A string containing potentially malformed JSON data. Can be a complete
                 JSON object, array, or partial JSON that needs repair.

    Returns:
        The parsed JSON structure (dict, list, str, or other JSON-compatible type) that
        represents the most meaningful interpretation of the input string. The return type
        depends on the input and which parsing strategy produces the better result.

    Example:
        >>> repair_json_with_best_structure('{"name": "John", "age": 30}')
        {'name': 'John', 'age': 30}

        >>> repair_json_with_best_structure('{"incomplete": "object"')
        {'incomplete': 'object'}

        >>> repair_json_with_best_structure('{"a": 1}{"b": 2}')
        [{'a': 1}, {'b': 2}]

    Note:
        This function is specifically designed for the structure-tool and uses the
        json_repair library's repair_json function with return_objects=True and
        ensure_ascii=False parameters.
    """
    parsed_as_is = repair_json(json_str=json_str, return_objects=True, ensure_ascii=False)
    parsed_with_wrap = repair_json(
        "[" + json_str + "]", return_objects=True, ensure_ascii=False
    )

    if all(isinstance(x, str) for x in (parsed_as_is, parsed_with_wrap)):
        return parsed_as_is

    if isinstance(parsed_as_is, str):
        return parsed_with_wrap
    if isinstance(parsed_with_wrap, str):
        return parsed_as_is

    if isinstance(parsed_with_wrap, list) and len(parsed_with_wrap) == 1:
        if parsed_with_wrap[0] == parsed_as_is:
            return parsed_as_is

    if isinstance(parsed_as_is, (dict, list)):
        if isinstance(parsed_with_wrap, list) and len(parsed_with_wrap) > 1:
            return parsed_with_wrap
        return parsed_as_is

    return parsed_with_wrap