from typing import Any

from requests import Response


class X2TextUtil:
    @staticmethod
    def get_value_for_key(key: str, form_data: dict[str, Any]) -> str:
        value: str = form_data.pop(key, None)
        return value

    @staticmethod
    def get_text_content(json_response: dict[str, Any]) -> str:
        combined_text: str = "\n".join(
            item["text"]
            for item in json_response  # type:ignore
        )
        return combined_text

    @staticmethod
    def read_response(response: Response) -> dict[str, Any]:
        if response.headers.get("Content-Type") == "application/json":
            return response.json()  # type: ignore
        else:
            return {"message": response.text}
