from typing import Any

from pluggable_apps.apps.table_settings.models import TableSettings


class PayloadModifier:

    @staticmethod
    def update(
        output: dict[str, Any],
        tool_id: str,
        prompt_id: str,
        prompt: str,
        input_file: str,
    ) -> dict[str, Any]:
        table_settings_object = TableSettings.objects.get(
            prompt_id=prompt_id, tool_id=tool_id
        )
        table_settings: dict[str, Any] = {}
        table_settings["headers"] = table_settings_object.headers
        table_settings["start_page"] = table_settings_object.start_page
        table_settings["end_page"] = table_settings_object.end_page
        table_settings["document_type"] = table_settings_object.document_type
        table_settings["compress_double_space"] = (
            table_settings_object.compress_double_space
        )
        table_settings["prompt"] = prompt
        table_settings["input_file"] = input_file
        output["table_settings"] = table_settings
        return output
