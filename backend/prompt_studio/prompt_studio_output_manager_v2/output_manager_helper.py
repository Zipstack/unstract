import json
import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from prompt_studio.lookup_utils import (
    attach_combined_output_enrichment,
    extract_prompt_output_enrichment,
    get_original_value_if_enriched,
    persist_lookup_output,
)
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
        profile_manager_id: str | None = None,
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
            challenge_data: dict[str, Any] | None,
            highlight_data: dict[str, Any] | None,
            confidence_data: dict[str, Any] | None,
            word_confidence_data: dict[str, Any] | None,
        ) -> PromptStudioOutputManager:
            """Handles creating or updating a single prompt output and returns
            the instance.
            """
            try:
                prompt_output, success = PromptStudioOutputManager.objects.get_or_create(
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
                        "highlight_data": highlight_data,
                        "confidence_data": confidence_data,
                        "word_confidence_data": word_confidence_data,
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

                args: dict[str, Any] = {
                    "run_id": run_id,
                    "output": output,
                    "eval_metrics": eval_metrics,
                    "context": context,
                    "challenge_data": challenge_data,
                    "highlight_data": highlight_data,
                    "confidence_data": confidence_data,
                    "word_confidence_data": word_confidence_data,
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
        highlight_data = metadata.get("highlight_data")
        confidence_data = metadata.get("confidence_data")
        word_confidence_data = metadata.get("word_confidence_data")

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

            # Use loop-scoped variables to avoid mutation
            prompt_context = context
            prompt_highlight_data = highlight_data
            prompt_confidence_data = confidence_data
            prompt_word_confidence_data = word_confidence_data
            prompt_challenge_data = challenge_data

            if not is_single_pass_extract:
                if prompt_context:
                    prompt_context = prompt_context.get(prompt.prompt_key)
                if prompt_highlight_data:
                    prompt_highlight_data = prompt_highlight_data.get(prompt.prompt_key)
                if prompt_confidence_data:
                    prompt_confidence_data = prompt_confidence_data.get(prompt.prompt_key)
                if prompt_word_confidence_data:
                    prompt_word_confidence_data = prompt_word_confidence_data.get(
                        prompt.prompt_key
                    )
                if prompt_challenge_data:
                    prompt_challenge_data = prompt_challenge_data.get(prompt.prompt_key)

            if prompt_challenge_data:
                prompt_challenge_data["file_name"] = metadata.get("file_name")

            # TODO: use enums here
            output = outputs.get(prompt.prompt_key)

            # On enrichment, store the raw LLM output here; the enriched
            # value is persisted separately via persist_lookup_output.
            enrichment = get_original_value_if_enriched(metadata, prompt.prompt_key)
            if enrichment is not None:
                output, prompt_lookup = enrichment
            else:
                prompt_lookup = None

            if prompt.enforce_type in {
                "json",
                "table",
                "record",
                "line-item",
                "agentic_table",
            }:
                output = json.dumps(output)
            eval_metrics = outputs.get(f"{prompt.prompt_key}__evaluation", [])
            profile_manager = default_profile

            # Update or create the prompt output
            prompt_output = update_or_create_prompt_output(
                prompt=prompt,
                profile_manager=profile_manager,
                output=output,
                eval_metrics=eval_metrics,
                tool=tool,
                context=json.dumps(prompt_context),
                challenge_data=prompt_challenge_data,
                highlight_data=prompt_highlight_data,
                confidence_data=prompt_confidence_data,
                word_confidence_data=prompt_word_confidence_data,
            )

            # Narrow except so plugin contract drift surfaces as a real
            # error instead of being masked as a successful save.
            if prompt_lookup:
                try:
                    persist_lookup_output(prompt_output, prompt_lookup)
                except (IntegrityError, ValidationError):
                    logger.error(
                        "Failed to persist lookup output for prompt %s",
                        prompt.prompt_key,
                        exc_info=True,
                    )

            # Serialize the instance
            serializer = PromptStudioOutputSerializer(prompt_output)
            serialized_data.append(serializer.data)

        return serialized_data

    @staticmethod
    def get_default_profile(
        profile_manager_id: str | None, tool: CustomTool
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
        tool_studio_prompts: list[ToolStudioPrompt],
        document_manager_id: str,
        use_default_profile: bool = False,
    ) -> dict[str, Any]:
        """Method to frame JSON responses for combined output for default for
        default profile manager of the project.

        Args:
            tool_studio_prompts (list[ToolStudioPrompt])
            document_manager_id (str)
            use_default_profile (bool)

        Returns:
            dict[str, Any]: Formatted JSON response for combined output.
                Cloud plugins may attach an opaque enrichment payload.
        """
        from prompt_studio.lookup_utils import enrich_prompt_output

        # Memoise default-profile resolution per tool to avoid N+1 on this
        # hot path (panel-switch latency).
        default_profile_cache: dict[str, str | None] = {}

        def _resolve(tool_prompt: ToolStudioPrompt) -> str | None:
            profile_manager_id = tool_prompt.profile_manager_id
            if profile_manager_id:
                return profile_manager_id
            if not use_default_profile:
                return None
            tool_id = tool_prompt.tool_id_id
            if tool_id not in default_profile_cache:
                try:
                    default_profile_cache[tool_id] = (
                        ProfileManager.get_default_llm_profile(
                            tool_prompt.tool_id
                        ).profile_id
                    )
                except DefaultProfileError:
                    default_profile_cache[tool_id] = None
            return default_profile_cache[tool_id]

        prompts_to_query: list[tuple[ToolStudioPrompt, str]] = []
        result: dict[str, Any] = {}
        for tool_prompt in tool_studio_prompts:
            if tool_prompt.prompt_type == PSOMKeys.NOTES:
                continue
            profile_manager_id = _resolve(tool_prompt)
            if profile_manager_id is None:
                result[tool_prompt.prompt_key] = ""
                continue
            prompts_to_query.append((tool_prompt, profile_manager_id))

        # ``DISTINCT ON`` (Postgres) yields the latest row per
        # (prompt_id, profile_manager_id) at the SQL layer.
        outputs_index: dict[tuple[str, str], PromptStudioOutputManager] = {}
        if prompts_to_query:
            prompt_ids = [str(p.prompt_id) for p, _ in prompts_to_query]
            profile_ids = list({pmid for _, pmid in prompts_to_query})
            outputs = (
                PromptStudioOutputManager.objects.filter(
                    prompt_id__in=prompt_ids,
                    profile_manager_id__in=profile_ids,
                    is_single_pass_extract=False,
                    document_manager_id=document_manager_id,
                )
                .order_by("prompt_id", "profile_manager_id", "-modified_at")
                .distinct("prompt_id", "profile_manager_id")
            )
            outputs_index = {
                (str(o.prompt_id), str(o.profile_manager_id)): o for o in outputs
            }

        enrichment_by_key: dict[str, Any] = {}
        for tool_prompt, profile_manager_id in prompts_to_query:
            output = outputs_index.get(
                (str(tool_prompt.prompt_id), str(profile_manager_id))
            )
            if output is None:
                result[tool_prompt.prompt_key] = ""
                continue
            result[tool_prompt.prompt_key] = output.output
            enriched = enrich_prompt_output(output, {})
            bundle = extract_prompt_output_enrichment(enriched)
            if bundle is not None:
                enrichment_by_key[tool_prompt.prompt_key] = bundle

        attach_combined_output_enrichment(result, enrichment_by_key)
        return result
