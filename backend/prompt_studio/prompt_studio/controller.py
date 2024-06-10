import logging

from prompt_studio.prompt_studio.constants import ToolStudioPromptKeys
from prompt_studio.prompt_studio.helper import PromptStudioHelper
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio.serializers import ReorderPromptsSerializer
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class PromptStudioController:
    def reorder_prompts(self, request: Request) -> Response:
        """Reorder the sequence of prompts based on the start and end sequence
        numbers.

        This action handles the reordering of prompts by updating their sequence
        numbers. It increments or decrements the sequence numbers of the relevant
        prompts to reflect the new order. If the start and end sequence numbers
        are equal, it returns a bad request response.

        Args:
            request (Request): The HTTP request object containing the data to
            reorder prompts.

        Returns:
            Response: A Response object with the status of the reordering operation.
        """
        try:
            # Validate request data
            serializer = ReorderPromptsSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Extract validated data from the serializer
            start_sequence_number = serializer.validated_data.get(
                ToolStudioPromptKeys.START_SEQUENCE_NUMBER
            )
            end_sequence_number = serializer.validated_data.get(
                ToolStudioPromptKeys.END_SEQUENCE_NUMBER
            )
            prompt_id = serializer.validated_data.get(ToolStudioPromptKeys.PROMPT_ID)

            filtered_prompts_data = PromptStudioHelper.reorder_prompts_helper(
                prompt_id=prompt_id,
                start_sequence_number=start_sequence_number,
                end_sequence_number=end_sequence_number,
            )

            logger.info("Re-ordering completed successfully.")
            return Response(status=status.HTTP_200_OK, data=filtered_prompts_data)

        except ToolStudioPrompt.DoesNotExist:
            logger.error(f"Prompt with ID {prompt_id} not found.")
            return Response(
                status=status.HTTP_404_NOT_FOUND, data={"detail": "Prompt not found."}
            )
