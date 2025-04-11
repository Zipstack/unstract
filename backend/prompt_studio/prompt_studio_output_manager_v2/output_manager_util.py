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
    ) -> list[str]:
        """Method to fetch coverage data for given tool and profile manager.

        Args:
            tool_id (str): The ID of the tool for which coverage is fetched.
            profile_manager_id (str): The ID of the profile manager
            for which coverage is calculated.
            prompt_id (Optional[str]): The ID of the prompt (optional).
            is_single_pass (Optional[bool]): Singlepass enabled or not.
            If provided, coverage is fetched for the specific prompt.

        Returns:
            dict[str, list[str]]: A dictionary containing coverage information.
                Keys are formatted as "coverage_<prompt_id>_<profile_manager_id>".
                Values are lists of document IDs associated with each prompt
                and profile combination.
        """
        # TODO: remove singlepass reference
        prompt_outputs = PromptStudioOutputManager.objects.filter(
            tool_id=tool_id,
            profile_manager_id=profile_manager_id,
            prompt_id=prompt_id,
            is_single_pass_extract=is_single_pass,
        ).values("prompt_id", "profile_manager_id", "document_manager_id")

        coverage = []
        for prompt_output in prompt_outputs:
            coverage.append(str(prompt_output["document_manager_id"]))
        return coverage
