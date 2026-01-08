"""Service for integrating Look-up enrichment with workflow execution.

This module provides Look-up enrichment for API/ETL/Workflow execution paths,
which are separate from the Prompt Studio UI path. It hooks into the
FileExecutionTasks pipeline to enrich extraction results before they are
sent to the destination.
"""

import logging
import uuid
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)


class LookupWorkflowIntegration:
    """Service for integrating Look-up enrichment with workflow execution.

    This service bridges the gap between workflow execution (API/ETL) and
    the Look-up enrichment system. In Prompt Studio UI, enrichment is handled
    by OutputManagerHelper._try_lookup_enrichment(). For workflows, this
    service provides equivalent functionality.

    The integration works by:
    1. Getting the Prompt Studio project ID from the workflow's tool instance
    2. Checking if any Look-up projects are linked to that PS project
    3. Executing the Look-up enrichment if links exist
    4. Merging the enrichment data with the extraction results
    """

    @staticmethod
    def get_prompt_studio_project_id(tool_instance_id: str) -> str | None:
        """Get the Prompt Studio project ID from a tool instance.

        The tool instance's tool_id is the PromptStudioRegistry's
        prompt_registry_id. The registry has a custom_tool FK to CustomTool,
        which is the actual Prompt Studio project.

        Args:
            tool_instance_id: UUID of the ToolInstance

        Returns:
            Prompt Studio project (CustomTool) UUID as string, or None if not found
        """
        from prompt_studio.prompt_studio_registry_v2.models import PromptStudioRegistry
        from tool_instance_v2.models import ToolInstance

        try:
            tool_instance = ToolInstance.objects.get(id=tool_instance_id)
            tool_id = tool_instance.tool_id

            # Check if this is a Prompt Studio exported tool
            try:
                registry = PromptStudioRegistry.objects.get(prompt_registry_id=tool_id)
                if registry.custom_tool:
                    return str(registry.custom_tool.tool_id)
            except (ObjectDoesNotExist, ValueError):
                # Not a Prompt Studio tool, or invalid UUID
                logger.debug(f"Tool {tool_id} is not a Prompt Studio exported tool")
                return None

        except ObjectDoesNotExist:
            logger.warning(f"ToolInstance {tool_instance_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting PS project ID: {e}")
            return None

        return None

    @staticmethod
    def get_prompt_studio_project_id_from_workflow(workflow_id: str) -> str | None:
        """Get the Prompt Studio project ID from a workflow's tool instances.

        Searches through the workflow's tool instances to find one that is
        a Prompt Studio exported tool.

        Args:
            workflow_id: UUID of the Workflow

        Returns:
            Prompt Studio project (CustomTool) UUID as string, or None if not found
        """
        from prompt_studio.prompt_studio_registry_v2.models import PromptStudioRegistry
        from tool_instance_v2.constants import ToolInstanceKey
        from tool_instance_v2.tool_instance_helper import ToolInstanceHelper

        try:
            tool_instances = ToolInstanceHelper.get_tool_instances_by_workflow(
                workflow_id, ToolInstanceKey.STEP
            )

            for tool_instance in tool_instances:
                tool_id = tool_instance.tool_id

                # Check if this is a Prompt Studio exported tool
                try:
                    registry = PromptStudioRegistry.objects.get(
                        prompt_registry_id=tool_id
                    )
                    if registry.custom_tool:
                        logger.debug(
                            f"Found PS project {registry.custom_tool.tool_id} "
                            f"for workflow {workflow_id}"
                        )
                        return str(registry.custom_tool.tool_id)
                except (ObjectDoesNotExist, ValueError):
                    # Not a Prompt Studio tool, continue to next
                    continue

            logger.debug(f"No Prompt Studio tool found in workflow {workflow_id}")
            return None

        except Exception as e:
            logger.error(f"Error getting PS project ID from workflow {workflow_id}: {e}")
            return None

    @staticmethod
    def has_lookup_links(prompt_studio_project_id: str) -> bool:
        """Check if a Prompt Studio project has any Look-up links.

        Args:
            prompt_studio_project_id: UUID of the Prompt Studio project

        Returns:
            True if Look-up links exist, False otherwise
        """
        from lookup.models import PromptStudioLookupLink

        try:
            return PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=prompt_studio_project_id
            ).exists()
        except Exception as e:
            logger.error(f"Error checking Look-up links: {e}")
            return False

    @staticmethod
    def enrich_workflow_output(
        workflow_id: str,
        extracted_data: dict[str, Any],
        file_execution_id: str | None = None,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute Look-up enrichment for workflow execution output.

        This method is the main entry point for workflow-based Look-up
        enrichment. It:
        1. Finds the Prompt Studio project from the workflow
        2. Checks for Look-up links
        3. Executes enrichment via LookupIntegrationService
        4. Returns the enrichment result

        Args:
            workflow_id: UUID of the workflow
            extracted_data: Dict of extracted field values from the tool
            file_execution_id: Optional file execution ID for tracking
            execution_id: Optional workflow execution ID for tracking

        Returns:
            Dict with 'lookup_enrichment' and '_lookup_metadata' keys,
            or empty dict if no enrichment was performed.
        """
        from lookup.services.lookup_integration_service import LookupIntegrationService

        if not extracted_data:
            logger.debug("No extracted data provided for workflow enrichment")
            return {}

        # Get the Prompt Studio project ID from the workflow
        ps_project_id = (
            LookupWorkflowIntegration.get_prompt_studio_project_id_from_workflow(
                workflow_id
            )
        )

        if not ps_project_id:
            logger.debug(f"No Prompt Studio project found for workflow {workflow_id}")
            return {}

        # Check if there are any Look-up links
        if not LookupWorkflowIntegration.has_lookup_links(ps_project_id):
            logger.debug(f"No Look-up links for PS project {ps_project_id}")
            return {}

        # Generate a run ID for tracking
        run_id = file_execution_id or execution_id or str(uuid.uuid4())

        logger.info(
            f"Executing Look-up enrichment for workflow {workflow_id}, "
            f"PS project {ps_project_id}, run_id {run_id}"
        )

        # Delegate to the existing LookupIntegrationService
        return LookupIntegrationService.enrich_if_linked(
            prompt_studio_project_id=ps_project_id,
            extracted_data=extracted_data,
            run_id=run_id,
        )

    @staticmethod
    def merge_enrichment_with_output(
        original_output: dict[str, Any] | str | None,
        enrichment_result: dict[str, Any],
    ) -> dict[str, Any] | str | None:
        """Merge Look-up enrichment data with the original tool output.

        The enrichment values REPLACE the corresponding fields in the original
        output. For example, if original has {"vendor_name": "Amzn Inc"} and
        enrichment has {"vendor_name": "AWS"}, the result will have
        {"vendor_name": "AWS"}.

        Args:
            original_output: Original tool output (dict, string, or None)
            enrichment_result: Result from enrich_workflow_output()

        Returns:
            Merged output with enrichment values replacing original fields
        """
        if not enrichment_result:
            return original_output

        lookup_enrichment = enrichment_result.get("lookup_enrichment", {})
        lookup_metadata = enrichment_result.get("_lookup_metadata", {})

        if not lookup_enrichment:
            return original_output

        # If original output is a string, try to parse it as JSON
        if isinstance(original_output, str):
            import json

            try:
                output_dict = json.loads(original_output)
            except json.JSONDecodeError:
                # Can't merge with non-JSON string, add enrichment as separate key
                return {
                    "extracted_data": original_output,
                    "lookup_enrichment": lookup_enrichment,
                    "_lookup_metadata": lookup_metadata,
                }
        elif isinstance(original_output, dict):
            output_dict = original_output.copy()
        elif original_output is None:
            output_dict = {}
        else:
            # Unknown type, wrap it
            output_dict = {"extracted_data": original_output}

        # REPLACE original field values with enriched values
        # This overwrites the original extracted values with the canonicalized ones
        #
        # Tool output structure is typically:
        # {"workflow_id": "...", "elapsed_time": ..., "output": {"vendor_name": "..."}}
        # We need to replace values INSIDE the "output" dict if it exists
        if "output" in output_dict and isinstance(output_dict["output"], dict):
            # Tool wrapped output - replace inside the "output" key
            for field_name, enriched_value in lookup_enrichment.items():
                if enriched_value is not None and field_name in output_dict["output"]:
                    logger.info(
                        f"Replacing output[{field_name}]: "
                        f"'{output_dict['output'].get(field_name)}' -> '{enriched_value}'"
                    )
                    output_dict["output"][field_name] = enriched_value
        else:
            # Flat structure - replace at root level
            for field_name, enriched_value in lookup_enrichment.items():
                if enriched_value is not None:
                    logger.info(
                        f"Replacing {field_name}: "
                        f"'{output_dict.get(field_name)}' -> '{enriched_value}'"
                    )
                    output_dict[field_name] = enriched_value

        # Add metadata for tracking (but not the separate lookup_enrichment key)
        output_dict["_lookup_metadata"] = lookup_metadata

        return output_dict

    @staticmethod
    def process_workflow_enrichment(
        workflow_id: str,
        original_output: dict[str, Any] | str | None,
        file_execution_id: str | None = None,
        execution_id: str | None = None,
    ) -> tuple[dict[str, Any] | str | None, bool]:
        """Complete Look-up enrichment process for workflow output.

        This is a convenience method that combines enrich_workflow_output()
        and merge_enrichment_with_output() into a single call.

        Args:
            workflow_id: UUID of the workflow
            original_output: Original tool output
            file_execution_id: Optional file execution ID
            execution_id: Optional workflow execution ID

        Returns:
            Tuple of (enriched_output, was_enriched)
        """
        # Extract data for enrichment - handle different output formats
        if isinstance(original_output, dict):
            extracted_data = original_output
        elif isinstance(original_output, str):
            import json

            try:
                extracted_data = json.loads(original_output)
            except json.JSONDecodeError:
                logger.debug("Cannot enrich non-JSON string output")
                return original_output, False
        else:
            logger.debug(f"Cannot enrich output of type {type(original_output)}")
            return original_output, False

        # Tool output structure is typically:
        # {"workflow_id": "...", "elapsed_time": ..., "output": {"vendor_name": "..."}}
        # We need to extract the "output" dict for enrichment if it exists
        if "output" in extracted_data and isinstance(extracted_data["output"], dict):
            data_for_enrichment = extracted_data["output"]
            logger.debug(
                f"Extracted 'output' key for enrichment: {list(data_for_enrichment.keys())}"
            )
        else:
            data_for_enrichment = extracted_data
            logger.debug(
                f"Using flat structure for enrichment: {list(data_for_enrichment.keys())}"
            )

        # Perform enrichment using the actual extraction data
        enrichment_result = LookupWorkflowIntegration.enrich_workflow_output(
            workflow_id=workflow_id,
            extracted_data=data_for_enrichment,
            file_execution_id=file_execution_id,
            execution_id=execution_id,
        )

        if not enrichment_result or not enrichment_result.get("lookup_enrichment"):
            return original_output, False

        # Merge results
        enriched_output = LookupWorkflowIntegration.merge_enrichment_with_output(
            original_output=original_output,
            enrichment_result=enrichment_result,
        )

        return enriched_output, True
