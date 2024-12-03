import json
from pathlib import Path
from typing import Any, Optional

from pluggable_apps.apps.table_settings_v2.models import TableSettings
from plugins.modifier.payload_modifier.exceptions import (
    PageRangeError,
    StartPageIndexError,
)


# TODO : Inherit this from a base class and override its methods here.
class PayloadModifier:
    CHOICES_JSON = "/static/select_choices.json"

    @staticmethod
    def update(
        output: dict[str, Any],
        tool_id: str,
        prompt_id: str,
        prompt: str,
        input_file: Optional[str] = None,
        clean_pages: bool = False,
    ) -> dict[str, Any]:
        table_settings_object: TableSettings = (
            PayloadModifier.configure_default_table_settings(tool_id, prompt_id)
        )
        table_settings: dict[str, Any] = {}
        start_page = table_settings_object.start_page
        end_page = table_settings_object.end_page
        if clean_pages:
            start_page, end_page = PayloadModifier.clean_extraction_span(
                start_page=start_page, end_page=end_page
            )
        table_settings["start_page"] = start_page
        table_settings["end_page"] = end_page
        table_settings["id"] = str(table_settings_object.id)
        table_settings["headers"] = table_settings_object.headers
        table_settings["document_type"] = table_settings_object.document_type
        table_settings["compress_double_space"] = (
            table_settings_object.compress_double_space
        )
        table_settings["disable_span_search"] = (
            table_settings_object.disable_span_search
        )
        table_settings["page_delimiter"] = table_settings_object.page_delimiter
        table_settings["use_form_feed"] = table_settings_object.use_form_feed
        table_settings["prompt"] = prompt
        table_settings["input_file"] = input_file
        output["table_settings"] = table_settings
        return output

    @staticmethod
    def clean_extraction_span(start_page: int, end_page: int) -> tuple[int, int]:
        # Support extraction of 10 pages in prompt studio for table/record
        if start_page < 0 or end_page < 0:
            raise PageRangeError()
        if end_page - start_page > 10:
            end_page = start_page + 9
        if start_page > end_page:
            raise StartPageIndexError()
        if end_page == 0 and start_page == 0:
            # To restrict the extraction to 10 pages in IDE,
            # this value is set as a flag for default value
            # for prompt studio to identify the source.
            end_page = -1
        return start_page, end_page

    @staticmethod
    def configure_default_table_settings(tool_id: str, prompt_id: str) -> TableSettings:
        if not TableSettings.objects.filter(
            prompt_id=prompt_id, tool_id=tool_id
        ).exists():
            # To create a default settings for table extraction
            TableSettings.objects.create(prompt_id=prompt_id, tool_id=tool_id)
        table_settings_object: TableSettings = TableSettings.objects.get(
            prompt_id=prompt_id, tool_id=tool_id
        )

        return table_settings_object

    @staticmethod
    def update_select_choices(default_choices: dict[str, Any]) -> dict[str, Any]:
        choices_json = Path(__file__).parent / "static" / "select_choices.json"
        with open(choices_json, encoding="utf-8") as file:
            choices_map: dict[str, str] = json.load(file)
        default_choices.update(choices_map)
        return default_choices
