import json
from typing import Any

from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_studio_output_manager.constants import (
    PromptStudioOutputManagerKeys as PSOMKeys,
)
from prompt_studio.prompt_studio_output_manager.models import (
    PromptStudioOutputManager,
)


class OutputManagerHelper:
    @staticmethod
    def handle_prompt_output_update(
        prompts: list[ToolStudioPrompt],
        outputs: Any,
        document_id: str,
        is_single_pass_extract: bool,
    ) -> None:
        """Handles updating prompt outputs in the database.

        Args:
            prompts (list[ToolStudioPrompt]): List of prompts to update.
            outputs (Any): Outputs corresponding to the prompts.
            document_id (str): ID of the document.
            is_single_pass_extract (bool):
            Flag indicating if single pass extract is active.
        """
        # Check if prompts list is empty
        if not prompts:
            return  # Return early if prompts list is empty

        tool = prompts[0].tool_id
        document_manager = DocumentManager.objects.get(pk=document_id)

        # Iterate through each prompt in the list
        for prompt in prompts:
            if prompt.prompt_type == PSOMKeys.NOTES:
                continue
            profile_manager = prompt.profile_manager
            output = json.dumps(outputs.get(prompt.prompt_key))
            eval_metrics = outputs.get(f"{prompt.prompt_key}__evaluation", [])

            # Attempt to update an existing output manager,
            # for the given criteria,
            # or create a new one if it doesn't exist
            PromptStudioOutputManager.objects.update_or_create(
                document_manager=document_manager,
                tool_id=tool,
                profile_manager=profile_manager,
                prompt_id=prompt,
                is_single_pass_extract=is_single_pass_extract,
                defaults={"output": output, "eval_metrics": eval_metrics},
            )
