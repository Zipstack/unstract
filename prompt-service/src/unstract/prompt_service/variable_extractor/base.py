from typing import Any

from .constants import VariableType
from .prompt_variable_service import VariableService


class VariableExtractor:

    @staticmethod
    def execute_variable_replacement(prompt: str, variable_map: dict[str, Any]) -> str:
        variables: list[str] = VariableService.extract_variables_from_prompt(
            prompt=prompt
        )
        for variable in variables:
            variable_type = VariableService.identify_variable_type(variable=variable)
            if variable_type == VariableType.STATIC:
                prompt = VariableService.replace_static_variable(
                    prompt=prompt, structured_output=variable_map, variable=variable
                )

            if variable_type == VariableType.DYNAMIC:
                prompt = VariableService.replace_dynamic_variable(
                    prompt=prompt, variable=variable, structured_output=variable_map
                )
        return prompt
