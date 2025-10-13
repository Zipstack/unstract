from typing import Any


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
