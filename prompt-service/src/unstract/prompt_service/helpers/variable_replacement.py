import json
import re
from functools import lru_cache
from typing import Any

from flask import current_app as app

from unstract.prompt_service.constants import VariableConstants, VariableType
from unstract.prompt_service.exceptions import CustomDataError
from unstract.prompt_service.utils.request import HTTPMethod, make_http_request


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
            app.logger.warning(
                f"Prompt with {variable} is not executed yet."
                " Unable to replace the variable"
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
        variable_type: VariableType

        # Check for custom_data variable type first
        custom_data_pattern = re.compile(VariableConstants.CUSTOM_DATA_VARIABLE_REGEX)
        if re.findall(custom_data_pattern, variable):
            variable_type = VariableType.CUSTOM_DATA
        else:
            # Check for dynamic variable type
            dynamic_pattern = re.compile(VariableConstants.DYNAMIC_VARIABLE_URL_REGEX)
            if re.findall(dynamic_pattern, variable):
                variable_type = VariableType.DYNAMIC
            else:
                variable_type = VariableType.STATIC
        return variable_type

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
        """Replace custom_data variable in prompt.

        Args:
            prompt: The prompt containing variables
            variable: The variable to replace (e.g., "custom_data.name")
            custom_data: The custom_data data dictionary
            is_ide: Whether this is running from Prompt Studio IDE (affects error messages)

        Returns:
            prompt with variable replaced
        """
        # Extract the path from custom_data.path.to.value
        custom_data_match = re.search(
            VariableConstants.CUSTOM_DATA_VARIABLE_REGEX, variable
        )
        if not custom_data_match:
            error_msg = "Invalid variable format."
            app.logger.error(f"{error_msg}: {variable}")
            raise CustomDataError(variable=variable, reason=error_msg, is_ide=is_ide)

        path_str = custom_data_match.group(1)
        path_parts = path_str.split(".")

        if not custom_data:
            error_msg = "Custom data is not configured."
            app.logger.error(error_msg)
            raise CustomDataError(variable=path_str, reason=error_msg, is_ide=is_ide)

        # Navigate through the nested dictionary
        try:
            value = custom_data
            for part in path_parts:
                value = value[part]
        except (KeyError, TypeError) as e:
            error_msg = f"Key '{path_str}' not found in custom data."
            app.logger.error(error_msg)
            raise CustomDataError(
                variable=path_str, reason=error_msg, is_ide=is_ide
            ) from e

        # Replace in prompt - let replace_generic_string_value handle formatting
        # (it only applies json.dumps for non-string values)
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
        """Internal cached extraction - returns tuple for lru_cache compatibility."""
        return tuple(re.findall(VariableConstants.VARIABLE_REGEX, prompt_text))

    @staticmethod
    def extract_variables_from_prompt(prompt_text: str) -> list[str]:
        """Extract variables from prompt with caching and stats logging.

        Uses lru_cache internally and logs cache statistics periodically
        to help determine if caching is beneficial.
        """
        result = VariableReplacementHelper._extract_variables_cached(prompt_text)

        # Log stats periodically (every 50 calls)
        info_after = VariableReplacementHelper._extract_variables_cached.cache_info()
        total_calls = info_after.hits + info_after.misses

        if total_calls % 50 == 0 and total_calls > 0:
            hit_rate = info_after.hits / total_calls * 100
            app.logger.info(
                f"[VariableCache] total={total_calls} hits={info_after.hits} "
                f"misses={info_after.misses} hit_rate={hit_rate:.1f}% "
                f"size={info_after.currsize}/{info_after.maxsize} "
                f"prompt_chars={len(prompt_text)}"
            )

        return list(result)

    @staticmethod
    def fetch_dynamic_variable_value(url: str, data: str) -> Any:
        # This prototype method currently supports
        # only endpoints that do not require authentication.
        # Additionally, it only accepts plain text
        # inputs for POST requests in this version.
        # Future versions may include support for
        #  authentication and other input formats.

        verb: HTTPMethod = HTTPMethod.POST
        headers = {"Content-Type": "text/plain"}
        response: Any = make_http_request(verb=verb, url=url, data=data, headers=headers)
        return response
