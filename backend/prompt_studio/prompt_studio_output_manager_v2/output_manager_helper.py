import json
import logging
from typing import Any

from account_v2.constants import Common
from django.core.exceptions import ObjectDoesNotExist
from utils.local_context import StateStore

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


def _build_prompt_lookup_map(
    prompts: list[ToolStudioPrompt],
) -> dict[str, str]:
    """Build mapping of prompt_key to lookup_project_id for prompts with lookups.

    Args:
        prompts: List of ToolStudioPrompt instances

    Returns:
        Dict mapping prompt_key to lookup_project_id (as string) for prompts
        that have a lookup_project assigned.
    """
    prompt_lookup_map: dict[str, str] = {}
    for prompt in prompts:
        if prompt.lookup_project_id:
            prompt_lookup_map[prompt.prompt_key] = str(prompt.lookup_project_id)
    return prompt_lookup_map


def _try_lookup_enrichment(
    tool_id: str,
    extracted_data: dict[str, Any],
    run_id: str | None = None,
    session_id: str | None = None,
    doc_name: str | None = None,
    prompt_lookup_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Attempt Lookup enrichment if available.

    This function safely attempts to enrich extracted data using linked
    Lookup projects. Returns empty dict if Lookup app is not available.

    Supports prompt-level lookups: if a field has a specific lookup assigned
    via prompt_lookup_map, only that lookup will enrich it. Fields without
    specific lookups will use all project-level linked lookups.

    Args:
        tool_id: Prompt Studio project (CustomTool) UUID
        extracted_data: Dict of extracted field values from prompts
        run_id: Optional execution run ID for tracking
        session_id: Optional WebSocket session ID for real-time log emission
        doc_name: Optional document name being processed
        prompt_lookup_map: Optional mapping of field names (prompt_key) to
            specific lookup_project_id for prompt-level lookup support

    Returns:
        Dict with 'lookup_enrichment' and '_lookup_metadata' keys,
        or empty dict if Lookup is not available or no links exist.
    """
    try:
        from utils.user_context import UserContext

        from lookup.services.lookup_integration_service import (
            LookupIntegrationService,
        )

        # Get organization ID from user context for RAG retrieval
        organization_id = UserContext.get_organization_identifier()

        return LookupIntegrationService.enrich_if_linked(
            prompt_studio_project_id=tool_id,
            extracted_data=extracted_data,
            run_id=run_id,
            session_id=session_id,
            doc_name=doc_name,
            organization_id=organization_id,
            prompt_lookup_map=prompt_lookup_map,
        )
    except ImportError:
        # Lookup app not installed
        logger.debug("Lookup app not available, skipping enrichment")
        return {}
    except Exception as e:
        # Don't let Lookup errors break PS execution
        logger.warning(f"Lookup enrichment failed (non-fatal): {e}")
        return {
            "lookup_enrichment": {},
            "_lookup_metadata": {
                "status": "error",
                "message": str(e),
            },
        }


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
            if prompt.enforce_type in {"json", "table", "record", "line-item"}:
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

            # Serialize the instance
            serializer = PromptStudioOutputSerializer(prompt_output)
            serialized_data.append(serializer.data)

        # Post-processing: Lookup enrichment integration
        # Build extracted data dict from all prompt outputs for enrichment
        extracted_data_for_lookup: dict[str, Any] = {}
        logger.info(
            f"Building extracted_data_for_lookup from {len(prompts)} prompts, "
            f"outputs keys: {list(outputs.keys())}"
        )
        for prompt in prompts:
            if prompt.prompt_type == PSOMKeys.NOTES:
                logger.debug(f"Skipping NOTES prompt: {prompt.prompt_key}")
                continue
            output_value = outputs.get(prompt.prompt_key)
            logger.info(
                f"Prompt {prompt.prompt_key}: output_value={output_value!r} "
                f"(type={type(output_value).__name__})"
            )
            if output_value is not None:
                extracted_data_for_lookup[prompt.prompt_key] = output_value

        logger.info(f"extracted_data_for_lookup: {extracted_data_for_lookup}")

        # Execute Lookup enrichment if linked projects exist
        if extracted_data_for_lookup:
            tool_id_str = str(tool.tool_id)
            logger.info(
                f"Calling Lookup enrichment for tool {tool_id_str} "
                f"with data: {extracted_data_for_lookup}"
            )
            # Get session_id for WebSocket log emission
            session_id = StateStore.get(Common.LOG_EVENTS_ID)
            doc_name = metadata.get("file_name") or document_manager.document_name

            # Build prompt-level lookup mapping for per-prompt lookup support
            prompt_lookup_map = _build_prompt_lookup_map(prompts)
            if prompt_lookup_map:
                logger.info(f"Using prompt-level lookups: {prompt_lookup_map}")

            lookup_result = _try_lookup_enrichment(
                tool_id=tool_id_str,
                extracted_data=extracted_data_for_lookup,
                run_id=run_id,
                session_id=session_id,
                doc_name=doc_name,
                prompt_lookup_map=prompt_lookup_map,
            )
            logger.info(f"Lookup enrichment result: {lookup_result}")

            # Replace output values with enriched values where applicable
            if lookup_result:
                lookup_enrichment = lookup_result.get("lookup_enrichment", {})
                lookup_metadata = lookup_result.get("_lookup_metadata", {})
                logger.info(
                    f"Applying lookup_enrichment={lookup_enrichment} "
                    f"to {len(serialized_data)} items"
                )

                for item in serialized_data:
                    prompt_key = item.get("prompt_key")
                    # If this prompt's field was enriched, replace the output value
                    if prompt_key and prompt_key in lookup_enrichment:
                        enriched_value = lookup_enrichment[prompt_key]
                        if enriched_value is not None:
                            original_value = item.get("output")
                            logger.info(
                                f"Replacing {prompt_key} output: "
                                f"'{original_value}' -> '{enriched_value}'"
                            )
                            # Store original value and enriched value for UI display
                            item["lookup_replacement"] = {
                                "original_value": original_value,
                                "enriched_value": enriched_value,
                                "field_name": prompt_key,
                            }
                            item["output"] = enriched_value
                    # Add metadata for tracking
                    item["_lookup_metadata"] = lookup_metadata

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
            if not profile_manager_id and not use_default_profile:
                result[tool_prompt.prompt_key] = ""
                continue

            if not profile_manager_id:
                default_profile = ProfileManager.get_default_llm_profile(
                    tool_prompt.tool_id
                )
                profile_manager_id = default_profile.profile_id

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
