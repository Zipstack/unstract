from .models import ToolStudioPrompt


class PromptStudioHelper:
    @staticmethod
    def update_sequence_numbers(filters: dict, increment: bool) -> list[dict[str, int]]:
        """Update the sequence numbers for prompts based on the provided
        filters and increment flag.

        Args:
            filters (Dict): The filter criteria for selecting prompts.
            increment (bool): Whether to increment (True)
            or decrement (False) the sequence numbers.

        Returns:
            List[Dict[str, int]]: A list of updated prompt data with their IDs
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
