from typing import Any

from flask import current_app as app
from unstract.prompt_service.constants import PromptServiceContants as PSKeys
from unstract.prompt_service.constants import RunLevel
from unstract.prompt_service.utils.log import publish_log
from unstract.sdk.constants import LogLevel

from .constants import VariableType
from .prompt_variable_service import VariableService


class VariableExtractor:

    @staticmethod
    def execute_variable_replacement(
        prompt_text: str, variable_map: dict[str, Any]
    ) -> str:
        variables: list[str] = VariableService.extract_variables_from_prompt(
            prompt=prompt_text
        )
        for variable in variables:
            variable_type = VariableService.identify_variable_type(variable=variable)
            if variable_type == VariableType.STATIC:
                prompt_text = VariableService.replace_static_variable(
                    prompt=prompt_text,
                    structured_output=variable_map,
                    variable=variable,
                )

            if variable_type == VariableType.DYNAMIC:
                prompt_text = VariableService.replace_dynamic_variable(
                    prompt=prompt_text,
                    variable=variable,
                    structured_output=variable_map,
                )
        return prompt_text

    @staticmethod
    def is_variables_present(prompt_text: str) -> bool:
        """Determines if variables are present in the prompt.

        Args:
            prompt (str): Prompt to check

        Returns:
            bool: True if variables are presentm else False
        """
        return bool(len(VariableService.extract_variables_from_prompt(prompt_text)))

    @staticmethod
    def replace_variables_in_prompt(
        prompt: dict[str, Any],
        structured_output: dict[str, Any],
        log_events_id: str,
        tool_id: str,
        prompt_name: str,
        doc_name: str,
    ) -> str:
        """Replaces variables in prompt.

        Args:
            log_events_id (str): UUID for the WS communication
            tool_id (str): UUID for the prompt studio project
            prompt_name (str): Name of the prompt being run
            doc_name (str): Name of the document being run with
            prompt (dict[str, Any]): Dict representing the prompt card
        Returns:
            prompt_text (str): Prompt with variables replaced
        """
        app.logger.info(f"[{tool_id}] Replacing variables in prompt : {prompt_name}")
        publish_log(
            log_events_id,
            {
                "tool_id": tool_id,
                "prompt_key": prompt_name,
                "doc_name": doc_name,
            },
            LogLevel.DEBUG,
            RunLevel.RUN,
            "Replacing variables in prompt",
        )
        try:
            variable_map = prompt[PSKeys.VARIABLE_MAP]
            prompt_text = VariableExtractor.execute_variable_replacement(
                prompt_text=prompt[PSKeys.PROMPT], variable_map=variable_map
            )
        except KeyError:
            # Executed incase of structured tool and
            # APIs where we do not set the variable map
            prompt_text = VariableExtractor.execute_variable_replacement(
                prompt_text=prompt_text, variable_map=structured_output
            )
        finally:
            app.logger.info(
                f"[{tool_id}] Prompt after variable replacement: {prompt_text}"
            )
            publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.DEBUG,
                RunLevel.RUN,
                f"Prompt after variable replacement:{prompt_text} ",
            )
        return prompt_text
