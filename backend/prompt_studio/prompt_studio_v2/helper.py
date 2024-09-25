import logging

from django.db import models

logger = logging.getLogger(__name__)


class PromptStudioHelper:
    @staticmethod
    def reorder_prompts_helper(
        prompt_id: str,
        start_sequence_number: int,
        end_sequence_number: int,
        prompt_model: models.Model,
    ) -> list[dict[str, int]]:
        """Helper method to reorder prompts based on sequence numbers.

        Args:
            prompt_id (str): The ID of the prompt to be reordered.
            start_sequence_number (int): The initial sequence number of the prompt.
            end_sequence_number (int): The new sequence number of the prompt.
            is_sps (bool): Flag to determine the prompt model to use.

        Returns:
            list[dict[str, int]]: A list of updated prompt data with their IDs
            and new sequence numbers.
        """

        prompt_instance = prompt_model.objects.get(pk=prompt_id)
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

        # Update sequence numbers and get filtered prompt data
        filtered_prompts_data = PromptStudioHelper.update_sequence_numbers(
            filters, increment, prompt_model
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
    def update_sequence_numbers(
        filters: dict, increment: bool, prompt_model: models.Model
    ) -> list[dict[str, int]]:
        """Update the sequence numbers for prompts based on the provided
        filters and increment flag.

        Args:
            filters (dict): The filter criteria for selecting prompts.
            increment (bool): Whether to increment (True) or decrement (False)
            the sequence numbers.
            prompt_model: The model class for the prompts
            (either ToolStudioPrompt or SPSPrompt).

        Returns:
            list[dict[str, int]]: A list of updated prompt data with their IDs
            and new sequence numbers.
        """
        filtered_prompts = prompt_model.objects.filter(**filters)

        # List to hold updated prompt data
        filtered_prompts_data = []

        # Prepare updates and collect data
        for prompt in filtered_prompts:
            prompt.sequence_number += 1 if increment else -1

            # Append prompt data to the list
            filtered_prompts_data.append(
                {
                    "id": prompt.prompt_id,
                    "sequence_number": prompt.sequence_number,
                }
            )

        # Bulk update the sequence numbers
        prompt_model.objects.bulk_update(filtered_prompts, ["sequence_number"])

        return filtered_prompts_data
