from typing import Any

from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_studio_output_manager.models import (
    PromptStudioOutputManager,
)


class OutputManagerHelper:
    @staticmethod
    def handle_prompt_output_update(
        prompts: list[ToolStudioPrompt],
        outputs: Any,
        document_id: str,
        is_single_pass_extract_mode_active: bool
    ) -> None:
        tool = prompts[0].tool_id
        document_manager = DocumentManager.objects.get(pk=document_id)

        # Iterate through each prompt in the list
        for prompt in prompts:
            profile_manager = prompt.profile_manager
            output = outputs.get(prompt.prompt_key)

            # Attempt to retrieve an existing output manager,
            # for the given criteria,
            # or create a new one if it doesn't exist
            output_manager, created = (
                PromptStudioOutputManager.objects.get_or_create(
                    document_manager=document_manager,
                    tool_id=tool,
                    profile_manager=profile_manager,
                    prompt_id=prompt,
                    is_single_pass_extract_mode_active=is_single_pass_extract_mode_active,
                    defaults={'output': output}
                )
            )

            # Update the output if it already exists
            if not created:
                output_manager.output = output
                output_manager.save()
