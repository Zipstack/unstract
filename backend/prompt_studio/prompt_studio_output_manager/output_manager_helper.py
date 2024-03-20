from typing import Any, Optional

from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_studio_output_manager.models import (
    PromptStudioOutputManager,
)


class OutputManagerHelper:
    @staticmethod
    def handle_prompt_output_update(prompts: list[ToolStudioPrompt], outputs: Any, document_id: str, is_single_pass_extract_mode_active) -> None:
        tool: CustomTool = prompts[0].tool_id
        document_manager: DocumentManager = DocumentManager.objects.get(
            pk=document_id)

        for prompt in prompts:
            profile_manager: ProfileManager = prompt.profile_manager

            try:
                output = outputs[prompt.prompt_key]
            except:
                output = None

            try:
                output_manager: Optional[PromptStudioOutputManager] = PromptStudioOutputManager.objects.get(
                    document_manager=document_manager, tool_id=tool, profile_manager=profile_manager, prompt_id=prompt.prompt_id, is_single_pass_extract_mode_active=is_single_pass_extract_mode_active
                )
            except:
                output_manager = None

            args: dict[str, str] = {
                "output": output,
            }

            if output_manager:
                # Handle Update
                PromptStudioOutputManager.objects.filter(
                    prompt_output_id=output_manager.prompt_output_id
                ).update(**args)
            else:
                # Handle Create
                args["prompt_id"] = prompt
                args["document_manager"] = document_manager
                args["profile_manager"] = profile_manager
                args["tool_id"] = tool
                args["is_single_pass_extract_mode_active"] = is_single_pass_extract_mode_active
                PromptStudioOutputManager.objects.create(**args)
