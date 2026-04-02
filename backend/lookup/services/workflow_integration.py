"""Workflow Integration Service for Look-up enrichment.

This module provides integration between Look-up enrichment and
workflow file execution (ETL, Workflow, API deployments).
It handles logging to both WebSocket (real-time) and ExecutionLog
(file-centric) based on execution context.
"""

import json
import logging
import uuid
from typing import Any
from uuid import UUID

from lookup.models import LookupExecutionAudit, PromptStudioLookupLink

logger = logging.getLogger(__name__)


class LookupWorkflowIntegration:
    """Service for integrating Look-ups with workflow file execution.

    This service provides methods to execute Look-ups within workflow
    contexts (ETL, Workflow, API) with proper logging and audit trail.

    Example:
        >>> from workflow_manager.file_execution.models import WorkflowFileExecution
        >>> file_exec = WorkflowFileExecution.objects.get(id=file_id)
        >>> result = LookupWorkflowIntegration.execute_lookups_for_file(
        ...     prompt_studio_project_id=ps_project_id,
        ...     extraction_output={"vendor": "Acme Corp"},
        ...     workflow_file_execution=file_exec,
        ...     organization_id="org-123",
        ... )
    """

    @classmethod
    def execute_lookups_for_file(
        cls,
        prompt_studio_project_id: UUID,
        extraction_output: dict[str, Any],
        workflow_execution_id: UUID,
        file_execution_id: UUID,
        organization_id: str,
        file_name: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute linked Look-ups for a file being processed in a workflow.

        This method is called from ETL, Workflow, and API execution pipelines
        after Prompt Studio extraction completes for a file.

        Args:
            prompt_studio_project_id: The PS project UUID
            extraction_output: Output from Prompt Studio extraction
            workflow_execution_id: The workflow execution UUID
            file_execution_id: The file execution UUID
            organization_id: Tenant organization ID
            file_name: Optional file name for logging
            session_id: Optional WebSocket session for real-time logs

        Returns:
            Enriched output with Look-up data merged, or original output
            if no Look-ups are linked or enrichment fails.
        """
        # Check for linked lookups first
        if not cls.has_linked_lookups(prompt_studio_project_id):
            logger.debug(f"No linked Look-ups for PS project {prompt_studio_project_id}")
            return extraction_output

        try:
            # Execute lookups using the integration service
            # LookupIntegrationService handles all logging via LookupLogEmitter
            from lookup.services.lookup_integration_service import (
                LookupIntegrationService,
            )

            result = LookupIntegrationService.enrich_if_linked(
                prompt_studio_project_id=str(prompt_studio_project_id),
                extracted_data=extraction_output,
                run_id=str(uuid.uuid4()),
                session_id=session_id,
                doc_name=file_name,
                file_execution_id=str(file_execution_id),
                workflow_execution_id=str(workflow_execution_id),
                organization_id=organization_id,
            )

            # Get enrichment result
            enrichment = result.get("lookup_enrichment", {})

            # Replace enriched values in extraction output (not add at top level)
            # The enrichment dict contains {field_name: enriched_value} pairs
            # These should replace the original values in extraction_output
            if enrichment:
                merged_output = extraction_output.copy()
                for field_name, enriched_value in enrichment.items():
                    if field_name in merged_output:
                        logger.info(
                            f"[LOOKUP] Replacing '{field_name}' value: "
                            f"'{merged_output[field_name]}' -> '{enriched_value}'"
                        )
                        merged_output[field_name] = enriched_value
                    else:
                        logger.warning(
                            f"[LOOKUP] Field '{field_name}' not found in extraction_output, "
                            f"skipping enrichment"
                        )
                return merged_output

            return extraction_output

        except Exception as e:
            logger.error(
                f"Look-up enrichment failed for file execution "
                f"{file_execution_id}: {e}",
                exc_info=True,
            )
            # Return original output on failure
            return extraction_output

    @classmethod
    def process_workflow_enrichment(
        cls,
        workflow_id: str,
        original_output: str,
        file_execution_id: str,
    ) -> tuple[str | dict[str, Any], bool]:
        """Process Look-up enrichment for workflow output.

        This method is called from file_execution_tasks._try_lookup_enrichment
        to enrich extraction output with Look-up data.

        Args:
            workflow_id: The workflow UUID as string
            original_output: The extraction output (JSON string or dict)
            file_execution_id: The file execution UUID as string

        Returns:
            Tuple of (enriched_output, was_enriched):
            - enriched_output: The enriched data (same type as input)
            - was_enriched: True if enrichment was applied
        """
        from prompt_studio.prompt_studio_registry_v2.models import PromptStudioRegistry
        from tool_instance_v2.models import ToolInstance
        from workflow_manager.file_execution.models import WorkflowFileExecution
        from workflow_manager.workflow_v2.models.workflow import Workflow

        try:
            logger.info(
                f"[LOOKUP] process_workflow_enrichment called for workflow "
                f"{workflow_id}, file_execution {file_execution_id}"
            )

            # Parse output if string
            if isinstance(original_output, str):
                try:
                    output_data = json.loads(original_output)
                    logger.info(
                        f"[LOOKUP] Parsed output data keys: {list(output_data.keys())}"
                    )
                except json.JSONDecodeError:
                    logger.warning(
                        f"[LOOKUP] Could not parse output as JSON for workflow {workflow_id}"
                    )
                    return original_output, False
            else:
                output_data = original_output
                logger.info(
                    f"[LOOKUP] Output data keys: {list(output_data.keys()) if isinstance(output_data, dict) else type(output_data)}"
                )

            # Get workflow and its prompt studio registry
            workflow = Workflow.objects.get(id=workflow_id)
            logger.info(f"[LOOKUP] Found workflow: {workflow.id}")

            # Get prompt studio project ID from workflow's tool instance
            # The tool_id in ToolInstance is the prompt_registry_id
            tool_instance = ToolInstance.objects.filter(workflow_id=workflow_id).first()

            if not tool_instance:
                logger.info(f"[LOOKUP] No tool instance found for workflow {workflow_id}")
                return original_output, False

            logger.info(
                f"[LOOKUP] Found tool instance: {tool_instance.id}, tool_id: {tool_instance.tool_id}"
            )

            # Get the PromptStudioRegistry to find the custom_tool (PS project)
            try:
                prompt_registry = PromptStudioRegistry.objects.get(
                    prompt_registry_id=tool_instance.tool_id
                )
                logger.info(
                    f"[LOOKUP] Found prompt registry: {prompt_registry.prompt_registry_id}"
                )
                if prompt_registry.custom_tool:
                    prompt_studio_project_id = str(prompt_registry.custom_tool.tool_id)
                    logger.info(
                        f"[LOOKUP] Found PS project ID: {prompt_studio_project_id}"
                    )
                else:
                    logger.info(
                        f"[LOOKUP] No custom tool linked to registry {tool_instance.tool_id}"
                    )
                    return original_output, False
            except PromptStudioRegistry.DoesNotExist:
                logger.info(
                    f"[LOOKUP] No prompt registry found for tool {tool_instance.tool_id}"
                )
                return original_output, False

            if not prompt_studio_project_id:
                logger.info(
                    f"[LOOKUP] No Prompt Studio project found for workflow {workflow_id}"
                )
                return original_output, False

            # Check for linked lookups
            if not cls.has_linked_lookups(UUID(prompt_studio_project_id)):
                logger.info(
                    f"[LOOKUP] No linked Look-ups for PS project {prompt_studio_project_id}"
                )
                return original_output, False

            logger.info(
                f"[LOOKUP] Found linked lookups for PS project {prompt_studio_project_id}"
            )

            # Get file execution for context
            file_execution = WorkflowFileExecution.objects.get(id=file_execution_id)
            workflow_execution_id = file_execution.workflow_execution_id
            organization_id = str(workflow.organization_id)

            # Extract the actual output data for enrichment
            # The workflow output structure is: {metadata: {...}, metrics: {...}, output: {...}}
            # The extracted fields are inside the 'output' key
            extracted_fields = output_data.get("output", {})
            if not extracted_fields or not isinstance(extracted_fields, dict):
                logger.info(
                    "[LOOKUP] No 'output' key found or not a dict in output_data, "
                    "trying to use output_data directly"
                )
                extracted_fields = output_data

            logger.info(
                f"[LOOKUP] Extracted fields for enrichment: {list(extracted_fields.keys())}"
            )

            # Execute lookups with file execution context for Nav bar logging
            # LookupIntegrationService handles all logging via LookupLogEmitter
            from lookup.services.lookup_integration_service import (
                LookupIntegrationService,
            )

            result = LookupIntegrationService.enrich_if_linked(
                prompt_studio_project_id=prompt_studio_project_id,
                extracted_data=extracted_fields,
                run_id=str(uuid.uuid4()),
                file_execution_id=file_execution_id,
                workflow_execution_id=str(workflow_execution_id),
                organization_id=organization_id,
                doc_name=file_execution.file_name,
            )

            # Get result metadata
            _metadata = result.get("_lookup_metadata", {})  # noqa F841
            enrichment = result.get("lookup_enrichment", {})

            # Replace enriched values in the output structure
            # The enrichment dict contains {field_name: enriched_value} pairs
            if enrichment:
                merged_output = output_data.copy()
                # Check if we need to update inside 'output' key or at top level
                if "output" in merged_output and isinstance(
                    merged_output["output"], dict
                ):
                    # Update inside the 'output' sub-object
                    merged_output["output"] = merged_output["output"].copy()
                    for field_name, enriched_value in enrichment.items():
                        if field_name in merged_output["output"]:
                            logger.info(
                                f"[LOOKUP] Replacing output['{field_name}'] value: "
                                f"'{merged_output['output'][field_name]}' -> '{enriched_value}'"
                            )
                            merged_output["output"][field_name] = enriched_value
                        else:
                            logger.warning(
                                f"[LOOKUP] Field '{field_name}' not found in output, "
                                f"skipping enrichment"
                            )
                else:
                    # Update at top level (fallback for flat structure)
                    for field_name, enriched_value in enrichment.items():
                        if field_name in merged_output:
                            logger.info(
                                f"[LOOKUP] Replacing '{field_name}' value: "
                                f"'{merged_output[field_name]}' -> '{enriched_value}'"
                            )
                            merged_output[field_name] = enriched_value
                        else:
                            logger.warning(
                                f"[LOOKUP] Field '{field_name}' not found in output_data, "
                                f"skipping enrichment"
                            )
                return merged_output, True

            return original_output, False

        except Exception as e:
            logger.error(
                f"Look-up enrichment failed for workflow {workflow_id}, "
                f"file execution {file_execution_id}: {e}",
                exc_info=True,
            )
            return original_output, False

    @classmethod
    def has_linked_lookups(cls, prompt_studio_project_id: UUID) -> bool:
        """Check if PS project has linked Look-ups.

        Args:
            prompt_studio_project_id: The PS project UUID

        Returns:
            True if at least one Look-up is linked
        """
        return PromptStudioLookupLink.objects.filter(
            prompt_studio_project_id=prompt_studio_project_id
        ).exists()

    @classmethod
    def _get_enabled_lookup_projects(cls, prompt_studio_project_id: UUID) -> list:
        """Get enabled lookup projects for a PS project.

        Args:
            prompt_studio_project_id: The PS project UUID

        Returns:
            List of enabled LookupProject instances
        """
        links = (
            PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=prompt_studio_project_id
            )
            .select_related("lookup_project")
            .order_by("execution_order")
        )

        return [link.lookup_project for link in links if link.is_enabled]

    @classmethod
    def get_lookup_logs_for_file(
        cls,
        file_execution_id: UUID,
    ) -> list[dict]:
        """Get all Look-up related logs for a file execution.

        Args:
            file_execution_id: The file execution UUID

        Returns:
            List of log dictionaries with data and event_time
        """
        from workflow_manager.workflow_v2.models import ExecutionLog

        return list(
            ExecutionLog.objects.filter(
                file_execution_id=file_execution_id,
                data__stage="LOOKUP",
            )
            .values("data", "event_time")
            .order_by("event_time")
        )

    @classmethod
    def get_lookup_audits_for_file(
        cls,
        file_execution_id: UUID,
    ) -> list[LookupExecutionAudit]:
        """Get all Look-up audit records for a file execution.

        Args:
            file_execution_id: The file execution UUID

        Returns:
            List of LookupExecutionAudit instances
        """
        return list(
            LookupExecutionAudit.objects.filter(file_execution_id=file_execution_id)
            .select_related("lookup_project")
            .order_by("executed_at")
        )

    @classmethod
    def get_lookup_audits_for_workflow(
        cls,
        workflow_execution_id: UUID,
    ) -> list[LookupExecutionAudit]:
        """Get all Look-up audit records for a workflow execution.

        Args:
            workflow_execution_id: The workflow execution UUID

        Returns:
            List of LookupExecutionAudit instances
        """
        # Get all file execution IDs for this workflow
        from workflow_manager.file_execution.models import WorkflowFileExecution

        file_execution_ids = WorkflowFileExecution.objects.filter(
            workflow_execution_id=workflow_execution_id
        ).values_list("id", flat=True)

        return list(
            LookupExecutionAudit.objects.filter(file_execution_id__in=file_execution_ids)
            .select_related("lookup_project")
            .order_by("executed_at")
        )
