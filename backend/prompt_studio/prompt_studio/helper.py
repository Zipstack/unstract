import logging

from prompt_studio.prompt_studio.models import ToolStudioPrompt

logger = logging.getLogger(__name__)


class PromptStudioHelper:
    @staticmethod
    def reorder_prompts_helper(
        prompt_id: str, start_sequence_number: int, end_sequence_number: int
    ) -> list[dict[str, int]]:
        """Helper method to reorder prompts based on sequence numbers.

        Args:
            prompt_id (str): The ID of the prompt to be reordered.
            start_sequence_number (int): The initial sequence number of the prompt.
            end_sequence_number (int): The new sequence number of the prompt.

        Returns:
            list[dict[str, int]]: A list of updated prompt data with their IDs
            and new sequence numbers.
        """
        prompt_instance: ToolStudioPrompt = ToolStudioPrompt.objects.get(pk=prompt_id)
        filtered_prompts_data = []
        tool_id = prompt_instance.tool_id

        # Determine the direction of sequence adjustment based on start
        # and end sequence numbers
        if start_sequence_number < end_sequence_number:
            logger.info(
                "Start sequence number is less than end sequence number. "
                "Decrementing sequence numbers."
            )
            filters = {
                "sequence_number__gt": start_sequence_number,
                "sequence_number__lte": end_sequence_number,
                "tool_id": tool_id,
            }
            increment = False

        elif start_sequence_number > end_sequence_number:
            logger.info(
                "Start sequence number is greater than end sequence number. "
                "Incrementing sequence numbers."
            )
            filters = {
                "sequence_number__lt": start_sequence_number,
                "sequence_number__gte": end_sequence_number,
                "tool_id": tool_id,
            }
            increment = True

        # Call helper method to update sequence numbers and get filtered prompt data
        filtered_prompts_data = PromptStudioHelper.update_sequence_numbers(
            filters, increment
        )

        # Update the sequence number of the moved prompt
        prompt_instance.sequence_number = end_sequence_number
        prompt_instance.save()

        # Append the updated prompt instance data to the response
        filtered_prompts_data.append(
            {
                "id": prompt_instance.prompt_id,
                "sequence_number": prompt_instance.sequence_number,
            }
        )

        return filtered_prompts_data

    @staticmethod
    def update_sequence_numbers(filters: dict, increment: bool) -> list[dict[str, int]]:
        """Update the sequence numbers for prompts based on the provided
        filters and increment flag.

        Args:
            filters (dict): The filter criteria for selecting prompts.
            increment (bool): Whether to increment (True) or decrement (False)
            the sequence numbers.

        Returns:
            list[dict[str, int]]: A list of updated prompt data with their IDs
            and new sequence numbers.
        """
        # Filter prompts based on the provided filters
        filtered_prompts = ToolStudioPrompt.objects.filter(**filters)

        # List to hold updated prompt data
        filtered_prompts_data = []

        # Prepare updates and collect data
        for prompt in filtered_prompts:
            if increment:
                prompt.sequence_number += 1
            else:
                prompt.sequence_number -= 1

            # Append prompt data to the list
            filtered_prompts_data.append(
                {
                    "id": prompt.prompt_id,
                    "sequence_number": prompt.sequence_number,
                }
            )

        # Bulk update the sequence numbers
        ToolStudioPrompt.objects.bulk_update(filtered_prompts, ["sequence_number"])

        return filtered_prompts_data
