import logging

from prompt_studio.prompt_studio.exceptions import AnswerFetchError
from simple_prompt_studio.sps_prompt.models import SPSPrompt
from simple_prompt_studio.sps_document.models import SPSDocument
from simple_prompt_studio.sps_prompt_output.models import SPSPromptOutput

logger = logging.getLogger(__name__)


class SPSPromptOutputHelper:
    @staticmethod
    def handle_prompt_output_update(
        prompt: SPSPrompt,
        output: str,
        document_manager: SPSDocument,
    ) -> None:        
        try:
            # Create or get the existing record for this document, prompt and
            # profile combo
            tool = prompt.tool_id
            _, success = SPSPromptOutput.objects.get_or_create(
                document_manager=document_manager,
                tool_id=tool,
                prompt_id=prompt,
                defaults={
                    "output": output,
                },
            )

            if success:
                logger.info(
                    f"Created record for prompt_id: {prompt.prompt_id}"
                )
            else:
                logger.info(
                    f"Updated record for prompt_id: {prompt.prompt_id}"
                )

            args: dict[str, str] = dict()
            args["output"] = output
            SPSPromptOutput.objects.filter(
                document_manager=document_manager,
                tool_id=tool,
                prompt_id=prompt,
            ).update(**args)

        except Exception as e:
            raise AnswerFetchError(f"Error updating prompt output {e}") from e
