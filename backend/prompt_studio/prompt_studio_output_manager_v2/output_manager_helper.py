import json
import logging
from typing import Any, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.exceptions import (
    AnswerFetchError,
    DefaultProfileError,
)
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_output_manager_v2.constants import (
    PromptStudioOutputManagerKeys as PSOMKeys,
)
from prompt_studio.prompt_studio_output_manager_v2.models import (
    PromptStudioOutputManager,
)
from prompt_studio.prompt_studio_output_manager_v2.serializers import (
    PromptStudioOutputSerializer,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt

logger = logging.getLogger(__name__)


class OutputManagerHelper:
    @staticmethod
    def handle_prompt_output_update(
        run_id: str,
        prompts: list[ToolStudioPrompt],
        outputs: Any,
        document_id: str,
        is_single_pass_extract: bool,
        metadata: dict[str, Any],
        profile_manager_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Handles updating prompt outputs in the database and returns
        serialized data.

        Args:
            run_id (str): ID of the run.
            prompts (list[ToolStudioPrompt]): List of prompts to update.
            outputs (Any): Outputs corresponding to the prompts.
            document_id (str): ID of the document.
            profile_manager_id (Optional[str]): UUID of the profile manager.
            is_single_pass_extract (bool): Flag indicating if single pass
            extract is active.
            metadata (dict[str, Any]): Metadata for the update.

        Returns:
            list[dict[str, Any]]: List of serialized prompt output data.
        """

        def update_or_create_prompt_output(
            prompt: ToolStudioPrompt,
            profile_manager: ProfileManager,
            output: str,
            eval_metrics: list[Any],
            tool: CustomTool,
            context: str,
            challenge_data: Optional[dict[str, Any]],
        ) -> PromptStudioOutputManager:
            """Handles creating or updating a single prompt output and returns
            the instance."""
            try:
                prompt_output, success = (
                    PromptStudioOutputManager.objects.get_or_create(
                        document_manager=document_manager,
                        tool_id=tool,
                        profile_manager=profile_manager,
                        prompt_id=prompt,
                        is_single_pass_extract=is_single_pass_extract,
                        defaults={
                            "output": output,
                            "eval_metrics": eval_metrics,
                            "context": context,
                            "challenge_data": challenge_data,
                        },
                    )
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

                args: dict[str, Any] = {
                    "run_id": run_id,
                    "output": output,
                    "eval_metrics": eval_metrics,
                    "context": context,
                    "challenge_data": challenge_data,
                }
                PromptStudioOutputManager.objects.filter(
                    document_manager=document_manager,
                    tool_id=tool,
                    profile_manager=profile_manager,
                    prompt_id=prompt,
                    is_single_pass_extract=is_single_pass_extract,
                ).update(**args)

                # Refresh the prompt_output instance to get updated values
                prompt_output.refresh_from_db()

                return prompt_output

            except Exception as e:
                raise AnswerFetchError(f"Error updating prompt output {e}") from e

        # List to store serialized results
        serialized_data: list[dict[str, Any]] = []
        context = metadata.get("context")
        challenge_data = metadata.get("challenge_data")

        if not prompts:
            return serialized_data

        tool = prompts[0].tool_id
        default_profile = OutputManagerHelper.get_default_profile(
            profile_manager_id, tool
        )
        document_manager = DocumentManager.objects.get(pk=document_id)

        for prompt in prompts:
            if prompt.prompt_type == PSOMKeys.NOTES:
                continue

            if not is_single_pass_extract:
                context = context.get(prompt.prompt_key)
                if challenge_data:
                    challenge_data = challenge_data.get(prompt.prompt_key)

            if challenge_data:
                challenge_data["file_name"] = metadata.get("file_name")

            output = outputs.get(prompt.prompt_key)
            # TODO: use enums here
            if prompt.enforce_type in {"json", "table", "record"}:
                output = json.dumps(output)
            profile_manager = default_profile
            eval_metrics = outputs.get(f"{prompt.prompt_key}__evaluation", [])

            # Update or create the prompt output
            prompt_output = update_or_create_prompt_output(
                prompt=prompt,
                profile_manager=profile_manager,
                output=output,
                eval_metrics=eval_metrics,
                tool=tool,
                context=json.dumps(context),
                challenge_data=challenge_data,
            )

            # Serialize the instance
            serializer = PromptStudioOutputSerializer(prompt_output)
            serialized_data.append(serializer.data)

        return serialized_data

    @staticmethod
    def get_default_profile(
        profile_manager_id: Optional[str], tool: CustomTool
    ) -> ProfileManager:
        if profile_manager_id:
            return OutputManagerHelper.fetch_profile_manager(profile_manager_id)
        else:
            return OutputManagerHelper.fetch_default_llm_profile(tool)

    @staticmethod
    def fetch_profile_manager(profile_manager_id: str) -> ProfileManager:
        try:
            return ProfileManager.objects.get(profile_id=profile_manager_id)
        except ProfileManager.DoesNotExist:
            raise DefaultProfileError(
                f"ProfileManager with ID {profile_manager_id} does not exist."
            )

    @staticmethod
    def fetch_default_llm_profile(tool: CustomTool) -> ProfileManager:
        try:
            return ProfileManager.get_default_llm_profile(tool=tool)
        except DefaultProfileError:
            raise DefaultProfileError("Default ProfileManager does not exist.")

    @staticmethod
    def fetch_default_output_response(
        tool_studio_prompts: list[ToolStudioPrompt], document_manager_id: str
    ) -> dict[str, Any]:
        """Method to frame JSON responses for combined output for default for
        default profile manager of the project.

        Args:
            tool_studio_prompts (list[ToolStudioPrompt])
            document_manager_id (str)

        Returns:
            dict[str, Any]: Formatted JSON response for combined output.
        """
        # Initialize the result dictionary
        result: dict[str, Any] = {}
        # Iterate over ToolStudioPrompt records
        for tool_prompt in tool_studio_prompts:
            if tool_prompt.prompt_type == PSOMKeys.NOTES:
                continue
            prompt_id = str(tool_prompt.prompt_id)
            profile_manager_id = tool_prompt.profile_manager_id

            # If profile_manager is not set, skip this record
            if not profile_manager_id:
                result[tool_prompt.prompt_key] = ""
                continue

            try:
                queryset = PromptStudioOutputManager.objects.filter(
                    prompt_id=prompt_id,
                    profile_manager=profile_manager_id,
                    is_single_pass_extract=False,
                    document_manager_id=document_manager_id,
                )

                if not queryset.exists():
                    result[tool_prompt.prompt_key] = ""
                    continue

                for output in queryset:
                    result[tool_prompt.prompt_key] = output.output
            except ObjectDoesNotExist:
                result[tool_prompt.prompt_key] = ""
        return result

    @staticmethod
    def get_coverage(
        tool_id: str, profile_manager_id: str, prompt_id: str = None
    ) -> dict[str, int]:
        """
        Method to fetch coverage data for given tool and profile manager.

        Args:
            tool (CustomTool): The tool instance or ID for which coverage is fetched.
            profile_manager_id (str): The ID of the profile manager
            for which coverage is calculated.
            prompt_id (Optional[str]): The ID of the prompt (optional).
            If provided, coverage is fetched for the specific prompt.

        Returns:
            dict[str, int]: A dictionary containing coverage information.
                Keys are formatted as "coverage_<prompt_id>_<profile_manager_id>".
                Values are the count of documents associated with each prompt
                and profile combination.
        """

        try:
            prompt_outputs = (
                PromptStudioOutputManager.objects.filter(
                    tool_id=tool_id,
                    profile_manager_id=profile_manager_id,
                    **({"prompt_id": prompt_id} if prompt_id else {}),
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
        except Exception as e:
            logger.error(f"Error occurred while fetching coverage: {e}")
        return {}
