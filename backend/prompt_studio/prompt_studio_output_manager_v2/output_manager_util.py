from django.db.models import Count
from prompt_studio.prompt_studio_output_manager_v2.models import (
    PromptStudioOutputManager,
)


class OutputManagerUtils:
    @staticmethod
    def get_coverage(
        tool_id: str,
        profile_manager_id: str,
        prompt_id: str = None,
        is_single_pass: bool = False,
    ) -> dict[str, int]:
        """
        Method to fetch coverage data for given tool and profile manager.

        Args:
            tool (CustomTool): The tool instance or ID for which coverage is fetched.
            profile_manager_id (str): The ID of the profile manager
            for which coverage is calculated.
            prompt_id (Optional[str]): The ID of the prompt (optional).
            is_single_pass (Optional[bool]): Singlepass enabled or not
            If provided, coverage is fetched for the specific prompt.

        Returns:
            dict[str, int]: A dictionary containing coverage information.
                Keys are formatted as "coverage_<prompt_id>_<profile_manager_id>".
                Values are the count of documents associated with each prompt
                and profile combination.
        """
        # TODO: remove singlepass reference
        prompt_outputs = (
            PromptStudioOutputManager.objects.filter(
                tool_id=tool_id,
                profile_manager_id=profile_manager_id,
                prompt_id=prompt_id,
                is_single_pass_extract=is_single_pass,
            )
            .values("prompt_id", "profile_manager_id")
            .annotate(document_count=Count("document_manager_id"))
        )

        coverage = {}
        for prompt_output in prompt_outputs:
            prompt_key = str(prompt_output["prompt_id"])
            profile_key = str(prompt_output["profile_manager_id"])
            coverage[f"coverage_{prompt_key}_{profile_key}"] = prompt_output[
                "document_count"
            ]
        return coverage
