import re
from enum import Enum
from typing import Any

from prompt_studio.prompt_studio_core_v2.exceptions import PromptNotRun
from prompt_studio.prompt_studio_output_manager_v2.models import (
    PromptStudioOutputManager,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt


class VariableType(str, Enum):
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"


class VariableConstants:
    VARIABLE_REGEX = "{{(.+?)}}"
    DYNAMIC_VARIABLE_DATA_REGEX = r"\[(.*?)\]"
    DYNAMIC_VARIABLE_URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"  # noqa: E501


class PromptStudioVariableService:
    @staticmethod
    def fetch_variable_outputs(variable: str, doc_id: str, tool_id: str) -> Any:
        variable_prompt: ToolStudioPrompt = ToolStudioPrompt.objects.get(
            prompt_key=variable, tool_id=tool_id
        )
        try:
            output = PromptStudioOutputManager.objects.get(
                prompt_id=variable_prompt.prompt_id,
                document_manager=doc_id,
                tool_id=variable_prompt.tool_id,
                profile_manager=variable_prompt.profile_manager,
                is_single_pass_extract=False,
            )
        except PromptStudioOutputManager.DoesNotExist:
            raise PromptNotRun(
                f"The prompt : {variable} must be executed before "
                "it can be used as a variable in another prompt. "
                "Please execute the prompt first and try again."
            )
        return output.output

    @staticmethod
    def identify_variable_type(variable: str) -> VariableType:
        variable_type: VariableType
        pattern = re.compile(VariableConstants.DYNAMIC_VARIABLE_URL_REGEX)
        if re.findall(pattern, variable):
            variable_type = VariableType.DYNAMIC
        else:
            variable_type = VariableType.STATIC
        return variable_type

    @staticmethod
    def extract_variables_from_prompt(prompt: str) -> list[str]:
        variable: list[str] = []
        variable = re.findall(VariableConstants.VARIABLE_REGEX, prompt)
        return variable

    @staticmethod
    def frame_variable_replacement_map(
        doc_id: str, prompt_object: ToolStudioPrompt
    ) -> dict[str, Any]:
        variable_output_map: dict[str, Any] = {}
        prompt = prompt_object.prompt
        variables = PromptStudioVariableService.extract_variables_from_prompt(
            prompt=prompt
        )
        for variable in variables:
            variable_type: VariableType = (
                PromptStudioVariableService.identify_variable_type(variable=variable)
            )
            if variable_type == VariableType.STATIC:
                variable_output_map[variable] = (
                    PromptStudioVariableService.fetch_variable_outputs(
                        variable=variable,
                        doc_id=doc_id,
                        tool_id=prompt_object.tool_id.tool_id,
                    )
                )
            if variable_type == VariableType.DYNAMIC:
                variable = re.findall(
                    VariableConstants.DYNAMIC_VARIABLE_DATA_REGEX, variable
                )[0]
                variable_output_map[variable] = (
                    PromptStudioVariableService.fetch_variable_outputs(
                        variable=variable,
                        doc_id=doc_id,
                        tool_id=prompt_object.tool_id.tool_id,
                    )
                )
        return variable_output_map
