from typing import Any


class X2TextUtil:
    @staticmethod
    def get_value_for_key(key: str, form_data: dict[str, Any]) -> str:
        value: str = form_data.pop(key, None)
        return value

    @staticmethod
    def get_text_content(json_response: dict[str, Any]) -> str:
        combined_text: str = "\n".join(
            item["text"] for item in json_response  # type:ignore
        )
        return combined_text
