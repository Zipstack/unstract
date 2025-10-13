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
    """Repair JSON string (structure-tool variant)."""
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