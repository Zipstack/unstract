"""Variable replacement for prompt templates.

Ported from prompt-service variable_replacement service + helper.
Flask dependencies (app.logger, publish_log) replaced with standard logging.
"""

import json
import logging
import re
from functools import lru_cache
from typing import Any

import requests as pyrequests
from requests.exceptions import RequestException

from executor.executors.constants import VariableConstants, VariableType
from executor.executors.exceptions import CustomDataError, LegacyExecutorError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VariableReplacementHelper — low-level replacement logic
# ---------------------------------------------------------------------------

class VariableReplacementHelper:
    @staticmethod
    def replace_static_variable(
        prompt: str, structured_output: dict[str, Any], variable: str
    ) -> str:
        output_value = VariableReplacementHelper.check_static_variable_run_status(
            structure_output=structured_output, variable=variable
        )
        if not output_value:
            return prompt
        static_variable_marker_string = "".join(["{{", variable, "}}"])
        replaced_prompt: str = VariableReplacementHelper.replace_generic_string_value(
            prompt=prompt, variable=static_variable_marker_string, value=output_value
        )
        return replaced_prompt

    @staticmethod
    def check_static_variable_run_status(
        structure_output: dict[str, Any], variable: str
    ) -> Any:
        output = None
        try:
            output = structure_output[variable]
        except KeyError:
            logger.warning(
                "Prompt with %s is not executed yet. "
                "Unable to replace the variable",
                variable,
            )
        return output

    @staticmethod
    def replace_generic_string_value(prompt: str, variable: str, value: Any) -> str:
        formatted_value: str = value
        if not isinstance(value, str):
            formatted_value = VariableReplacementHelper.handle_json_and_str_types(value)
        replaced_prompt = prompt.replace(variable, formatted_value)
        return replaced_prompt

    @staticmethod
    def handle_json_and_str_types(value: Any) -> str:
        try:
            formatted_value = json.dumps(value)
        except ValueError:
            formatted_value = str(value)
        return formatted_value

    @staticmethod
    def identify_variable_type(variable: str) -> VariableType:
        custom_data_pattern = re.compile(VariableConstants.CUSTOM_DATA_VARIABLE_REGEX)
        if re.findall(custom_data_pattern, variable):
            return VariableType.CUSTOM_DATA

        dynamic_pattern = re.compile(VariableConstants.DYNAMIC_VARIABLE_URL_REGEX)
        if re.findall(dynamic_pattern, variable):
            return VariableType.DYNAMIC

        return VariableType.STATIC

    @staticmethod
    def replace_dynamic_variable(
        prompt: str, variable: str, structured_output: dict[str, Any]
    ) -> str:
        url = re.search(VariableConstants.DYNAMIC_VARIABLE_URL_REGEX, variable).group(0)
        data = re.findall(VariableConstants.DYNAMIC_VARIABLE_DATA_REGEX, variable)[0]
        output_value = VariableReplacementHelper.check_static_variable_run_status(
            structure_output=structured_output, variable=data
        )
        if not output_value:
            return prompt
        api_response: Any = VariableReplacementHelper.fetch_dynamic_variable_value(
            url=url, data=output_value
        )
        formatted_api_response: str = VariableReplacementHelper.handle_json_and_str_types(
            api_response
        )
        static_variable_marker_string = "".join(["{{", variable, "}}"])
        replaced_prompt: str = VariableReplacementHelper.replace_generic_string_value(
            prompt=prompt,
            variable=static_variable_marker_string,
            value=formatted_api_response,
        )
        return replaced_prompt

    @staticmethod
    def replace_custom_data_variable(
        prompt: str,
        variable: str,
        custom_data: dict[str, Any],
        is_ide: bool = True,
    ) -> str:
        custom_data_match = re.search(
            VariableConstants.CUSTOM_DATA_VARIABLE_REGEX, variable
        )
        if not custom_data_match:
            error_msg = "Invalid variable format."
            logger.error("%s: %s", error_msg, variable)
            raise CustomDataError(variable=variable, reason=error_msg, is_ide=is_ide)

        path_str = custom_data_match.group(1)
        path_parts = path_str.split(".")

        if not custom_data:
            error_msg = "Custom data is not configured."
            logger.error(error_msg)
            raise CustomDataError(variable=path_str, reason=error_msg, is_ide=is_ide)

        try:
            value = custom_data
            for part in path_parts:
                value = value[part]
        except (KeyError, TypeError) as e:
            error_msg = f"Key '{path_str}' not found in custom data."
            logger.error(error_msg)
            raise CustomDataError(
                variable=path_str, reason=error_msg, is_ide=is_ide
            ) from e

        variable_marker_string = "".join(["{{", variable, "}}"])
        replaced_prompt = VariableReplacementHelper.replace_generic_string_value(
            prompt=prompt,
            variable=variable_marker_string,
            value=value,
        )
        return replaced_prompt

    @staticmethod
    @lru_cache(maxsize=128)
    def _extract_variables_cached(prompt_text: str) -> tuple[str, ...]:
        return tuple(re.findall(VariableConstants.VARIABLE_REGEX, prompt_text))

    @staticmethod
    def extract_variables_from_prompt(prompt_text: str) -> list[str]:
        result = VariableReplacementHelper._extract_variables_cached(prompt_text)
        return list(result)

    @staticmethod
    def fetch_dynamic_variable_value(url: str, data: str) -> Any:
        """Fetch dynamic variable value from an external URL.

        Ported from prompt-service make_http_request — simplified to direct
        requests.post since we don't need Flask error classes.
        """
        headers = {"Content-Type": "text/plain"}
        try:
            response = pyrequests.post(url, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            if response.headers.get("content-type") == "application/json":
                return response.json()
            return response.text
        except RequestException as e:
            logger.error("HTTP request error fetching dynamic variable: %s", e)
            status_code = None
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
            raise LegacyExecutorError(
                message=f"HTTP POST to {url} failed: {e!s}",
                code=status_code or 500,
            ) from e


# ---------------------------------------------------------------------------
# VariableReplacementService — high-level orchestration
# ---------------------------------------------------------------------------

class VariableReplacementService:
    @staticmethod
    def is_variables_present(prompt_text: str) -> bool:
        return bool(
            len(VariableReplacementHelper.extract_variables_from_prompt(prompt_text))
        )

    @staticmethod
    def replace_variables_in_prompt(
        prompt: dict[str, Any],
        structured_output: dict[str, Any],
        prompt_name: str,
        tool_id: str = "",
        log_events_id: str = "",
        doc_name: str = "",
        custom_data: dict[str, Any] | None = None,
        is_ide: bool = True,
    ) -> str:
        from executor.executors.constants import PromptServiceConstants as PSKeys

        logger.info("[%s] Replacing variables in prompt: %s", tool_id, prompt_name)

        prompt_text = prompt[PSKeys.PROMPT]
        try:
            variable_map = prompt[PSKeys.VARIABLE_MAP]
            prompt_text = VariableReplacementService._execute_variable_replacement(
                prompt_text=prompt[PSKeys.PROMPT],
                variable_map=variable_map,
                custom_data=custom_data,
                is_ide=is_ide,
            )
        except KeyError:
            prompt_text = VariableReplacementService._execute_variable_replacement(
                prompt_text=prompt_text,
                variable_map=structured_output,
                custom_data=custom_data,
                is_ide=is_ide,
            )
        return prompt_text

    @staticmethod
    def _execute_variable_replacement(
        prompt_text: str,
        variable_map: dict[str, Any],
        custom_data: dict[str, Any] | None = None,
        is_ide: bool = True,
    ) -> str:
        variables: list[str] = VariableReplacementHelper.extract_variables_from_prompt(
            prompt_text=prompt_text
        )
        for variable in variables:
            variable_type = VariableReplacementHelper.identify_variable_type(
                variable=variable
            )
            if variable_type == VariableType.STATIC:
                prompt_text = VariableReplacementHelper.replace_static_variable(
                    prompt=prompt_text,
                    structured_output=variable_map,
                    variable=variable,
                )
            elif variable_type == VariableType.DYNAMIC:
                prompt_text = VariableReplacementHelper.replace_dynamic_variable(
                    prompt=prompt_text,
                    variable=variable,
                    structured_output=variable_map,
                )
            elif variable_type == VariableType.CUSTOM_DATA:
                prompt_text = VariableReplacementHelper.replace_custom_data_variable(
                    prompt=prompt_text,
                    variable=variable,
                    custom_data=custom_data or {},
                    is_ide=is_ide,
                )
        return prompt_text
