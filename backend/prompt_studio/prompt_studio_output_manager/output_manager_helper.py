import json
import logging
from typing import Any, Optional

from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.exceptions import (
    AnswerFetchError,
    DefaultProfileError,
)
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_studio_output_manager.constants import (
    PromptStudioOutputManagerKeys as PSOMKeys,
)
from prompt_studio.prompt_studio_output_manager.models import PromptStudioOutputManager

logger = logging.getLogger(__name__)


class OutputManagerHelper:
    @staticmethod
    def handle_prompt_output_update(
        run_id: str,
        prompts: list[ToolStudioPrompt],
        outputs: Any,
        document_id: str,
        is_single_pass_extract: bool,
        profile_manager_id: Optional[str] = None,
        tool: CustomTool = None,
    ) -> None:
        """Handles updating prompt outputs in the database.

        Args:
            run_id (str): ID of the run.
            prompts (list[ToolStudioPrompt]): List of prompts to update.
            outputs (Any): Outputs corresponding to the prompts.
            document_id (str): ID of the document.
            profile_manager_id (Optional[str]): UUID of the profile manager.
            is_single_pass_extract (bool):
            Flag indicating if single pass extract is active.
            tool (CustomTool, optional): Custom tool used for extracting.
        """

        def get_default_profile():
            if profile_manager_id:
                try:
                    return ProfileManager.objects.get(profile_id=profile_manager_id)
                except ProfileManager.DoesNotExist:
                    raise DefaultProfileError(
                        f"ProfileManager with ID {profile_manager_id} does not exist."
                    )
            else:
                if tool:
                    return ProfileManager.get_default_llm_profile(tool=tool)
                else:
                    raise DefaultProfileError(
                        f"ProfileManager with ID {profile_manager_id} does not exist."
                    )

        def update_or_create_prompt_output(
            prompt, profile_manager, output, eval_metrics
        ):
            try:
                _, success = PromptStudioOutputManager.objects.get_or_create(
                    document_manager=document_manager,
                    tool_id=tool,
                    profile_manager=profile_manager,
                    prompt_id=prompt,
                    is_single_pass_extract=is_single_pass_extract,
                    defaults={
                        "output": output,
                        "eval_metrics": eval_metrics,
                    },
                )

                if success:
                    logger.info(
                        f"Created record for prompt_id: {prompt.prompt_id} and "
                        f"profile {profile_manager.profile_id}"
                    )
                else:
                    logger.info(
                        f"Updated record for prompt_id: {prompt.prompt_id} and "
                        f"profile {profile_manager.profile_id}"
                    )

                args: dict[str, str] = {
                    "run_id": run_id,
                    "output": output,
                    "eval_metrics": eval_metrics,
                }
                PromptStudioOutputManager.objects.filter(
                    document_manager=document_manager,
                    tool_id=tool,
                    profile_manager=profile_manager,
                    prompt_id=prompt,
                    is_single_pass_extract=is_single_pass_extract,
                ).update(**args)

            except Exception as e:
                raise AnswerFetchError(f"Error updating prompt output {e}") from e

        if not prompts:
            return  # Return early if prompts list is empty

        default_profile = get_default_profile()
        tool = prompts[0].tool_id
        document_manager = DocumentManager.objects.get(pk=document_id)

        for prompt in prompts:
            if prompt.prompt_type == PSOMKeys.NOTES:
                continue

            profile_manager = default_profile
            output = json.dumps(outputs.get(prompt.prompt_key))
            eval_metrics = outputs.get(f"{prompt.prompt_key}__evaluation", [])

            update_or_create_prompt_output(
                prompt, profile_manager, output, eval_metrics
            )
