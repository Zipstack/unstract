"""Service for automatic Lookup integration with Prompt Studio.

This module provides seamless enrichment of extraction results when Lookup
projects are linked to a Prompt Studio project. It executes automatically
after PS extraction completes.
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Configuration defaults
LOOKUP_AUTO_ENRICH_ENABLED = getattr(settings, "LOOKUP_AUTO_ENRICH_ENABLED", True)
LOOKUP_ENRICHMENT_TIMEOUT = getattr(settings, "LOOKUP_ENRICHMENT_TIMEOUT", 30)


class LookupIntegrationService:
    """Service for automatic Lookup integration with Prompt Studio.

    Provides seamless enrichment of extraction results when Lookup
    projects are linked to a Prompt Studio project.
    """

    @staticmethod
    def enrich_if_linked(
        prompt_studio_project_id: str,
        extracted_data: dict[str, Any],
        run_id: str | None = None,
        timeout: float | None = None,
        session_id: str | None = None,
        doc_name: str | None = None,
        file_execution_id: str | None = None,
        workflow_execution_id: str | None = None,
        organization_id: str | None = None,
        prompt_lookup_map: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute Lookup enrichment if PS project has linked Lookups.

        Features:
        - Zero overhead if no links exist
        - Timeout protection to not block extraction
        - Graceful degradation on errors
        - Full audit logging
        - WebSocket log emission for Prompt Studio UI
        - ExecutionLog persistence for Nav bar display (workflow context)
        - Prompt-level lookup support: specific lookups per field

        Args:
            prompt_studio_project_id: UUID of Prompt Studio project
            extracted_data: Dict of extracted field values
            run_id: Optional execution run ID for tracking
            timeout: Max seconds to wait (default from settings)
            session_id: WebSocket session ID for real-time log emission
            doc_name: Document name being processed
            file_execution_id: File execution ID for Nav bar logs
            workflow_execution_id: Workflow execution ID for Nav bar logs
            organization_id: Organization ID for multi-tenancy
            prompt_lookup_map: Optional mapping of field names (prompt_key) to
                specific lookup_project_id. Fields with a specific lookup will
                ONLY be enriched by that lookup. Fields without a specific
                lookup will use all project-level linked lookups.

        Returns:
            Dict with 'lookup_enrichment' and '_lookup_metadata' keys,
            or empty dict if no links or enrichment disabled.
        """
        # Check if auto-enrichment is enabled
        if not LOOKUP_AUTO_ENRICH_ENABLED:
            logger.debug("Lookup auto-enrichment is disabled")
            return {}

        if not extracted_data:
            logger.debug("No extracted data provided for enrichment")
            return {}

        timeout = timeout or LOOKUP_ENRICHMENT_TIMEOUT
        prompt_lookup_map = prompt_lookup_map or {}

        try:
            return LookupIntegrationService._execute_enrichment(
                prompt_studio_project_id=prompt_studio_project_id,
                extracted_data=extracted_data,
                run_id=run_id,
                timeout=timeout,
                session_id=session_id,
                doc_name=doc_name,
                file_execution_id=file_execution_id,
                workflow_execution_id=workflow_execution_id,
                organization_id=organization_id,
                prompt_lookup_map=prompt_lookup_map,
            )
        except FuturesTimeoutError:
            logger.warning(
                f"Lookup enrichment timed out for PS project "
                f"{prompt_studio_project_id} after {timeout}s"
            )
            return {
                "lookup_enrichment": {},
                "_lookup_metadata": {
                    "status": "timeout",
                    "message": f"Enrichment timed out after {timeout}s",
                    "lookups_executed": 0,
                    "lookups_successful": 0,
                },
            }
        except Exception as e:
            logger.error(
                f"Lookup enrichment failed for PS project "
                f"{prompt_studio_project_id}: {e}",
                exc_info=True,
            )
            return {
                "lookup_enrichment": {},
                "_lookup_metadata": {
                    "status": "error",
                    "message": str(e),
                    "lookups_executed": 0,
                    "lookups_successful": 0,
                },
            }

    @staticmethod
    def _execute_enrichment(
        prompt_studio_project_id: str,
        extracted_data: dict[str, Any],
        run_id: str | None,
        timeout: float,
        session_id: str | None = None,
        doc_name: str | None = None,
        file_execution_id: str | None = None,
        workflow_execution_id: str | None = None,
        organization_id: str | None = None,
        prompt_lookup_map: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Internal method to execute enrichment with timeout.

        Args:
            prompt_lookup_map: Mapping of field names to specific lookup project IDs.
                Fields in this map will only be enriched by their specific lookup.
        """
        from lookup.models import PromptStudioLookupLink
        from lookup.services.log_emitter import LookupLogEmitter

        # Initialize log emitter for WebSocket and/or ExecutionLog
        # When file_execution_id is set (workflow context), logs persist to Nav bar
        log_emitter = LookupLogEmitter(
            session_id=session_id,
            execution_id=workflow_execution_id or run_id,
            file_execution_id=file_execution_id,
            organization_id=organization_id,
            doc_name=doc_name,
        )

        # Quick existence check - minimal overhead if no links
        links = (
            PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=prompt_studio_project_id
            )
            .select_related("lookup_project")
            .order_by("execution_order")
        )

        if not links.exists():
            logger.debug(
                f"No Lookup links found for PS project {prompt_studio_project_id}"
            )
            log_emitter.emit_no_linked_lookups()
            return {}

        # Get enabled lookup projects (those with ready status)
        lookup_projects = [link.lookup_project for link in links if link.is_enabled]

        if not lookup_projects:
            logger.debug(
                f"No enabled Lookup projects for PS project {prompt_studio_project_id}"
            )
            return {}

        logger.info(
            f"Executing {len(lookup_projects)} Lookup(s) for PS project "
            f"{prompt_studio_project_id}"
        )

        # Emit orchestration start log
        lookup_names = [lp.name for lp in lookup_projects]
        log_emitter.emit_orchestration_start(
            lookup_count=len(lookup_projects),
            lookup_names=lookup_names,
        )

        # Execute with timeout protection
        import time

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                LookupIntegrationService._run_orchestrator,
                lookup_projects=lookup_projects,
                input_data=extracted_data,
                execution_id=run_id or str(uuid.uuid4()),
                prompt_studio_project_id=prompt_studio_project_id,
                log_emitter=log_emitter,
                organization_id=organization_id,
                prompt_lookup_map=prompt_lookup_map or {},
            )
            result = future.result(timeout=timeout)

        # Emit orchestration complete log
        total_time_ms = int((time.time() - start_time) * 1000)
        metadata = result.get("_lookup_metadata", {})
        log_emitter.emit_orchestration_complete(
            total_lookups=len(lookup_projects),
            successful=metadata.get("lookups_successful", 0),
            failed=metadata.get("lookups_executed", 0)
            - metadata.get("lookups_successful", 0),
            total_time_ms=total_time_ms,
            total_enriched_fields=len(result.get("lookup_enrichment", {})),
        )

        return result

    @staticmethod
    def _run_orchestrator(
        lookup_projects: list,
        input_data: dict[str, Any],
        execution_id: str,
        prompt_studio_project_id: str,
        log_emitter: Any = None,
        organization_id: str | None = None,
        prompt_lookup_map: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute the lookup orchestrator for all linked projects.

        Supports prompt-level lookups: if a field has a specific lookup assigned
        via prompt_lookup_map, only that lookup will enrich it. Fields without
        specific lookups will use all project-level linked lookups.

        Args:
            lookup_projects: List of LookupProject instances linked at project level
            input_data: Dict of extracted field values
            execution_id: Execution run ID for tracking
            prompt_studio_project_id: UUID of Prompt Studio project
            log_emitter: Optional log emitter for WebSocket logs
            organization_id: Organization ID for multi-tenancy
            prompt_lookup_map: Mapping of field names to specific lookup project IDs
        """
        from lookup.integrations.file_storage_client import FileStorageClient
        from lookup.integrations.unstract_llm_client import UnstractLLMClient
        from lookup.models import LookupProfileManager
        from lookup.services.enrichment_merger import EnrichmentMerger
        from lookup.services.llm_cache import LLMResponseCache
        from lookup.services.lookup_executor import LookUpExecutor
        from lookup.services.lookup_orchestrator import LookUpOrchestrator
        from lookup.services.reference_data_loader import ReferenceDataLoader
        from lookup.services.variable_resolver import VariableResolver

        try:
            # Get profile manager for LLM client
            # Use the first lookup project's default profile
            first_project = lookup_projects[0]
            profile_manager = LookupProfileManager.objects.filter(
                lookup_project=first_project, is_default=True
            ).first()

            if not profile_manager:
                logger.warning(
                    f"No default profile for Lookup project {first_project.id}"
                )
                return {
                    "lookup_enrichment": {},
                    "_lookup_metadata": {
                        "status": "error",
                        "message": "No LLM profile configured for Lookup project",
                        "lookups_executed": 0,
                        "lookups_successful": 0,
                    },
                }

            # Get LLM adapter instance from profile
            llm_adapter_instance = profile_manager.llm
            if not llm_adapter_instance:
                logger.warning("No LLM adapter configured in profile")
                return {
                    "lookup_enrichment": {},
                    "_lookup_metadata": {
                        "status": "error",
                        "message": "No LLM adapter configured",
                        "lookups_executed": 0,
                        "lookups_successful": 0,
                    },
                }

            # Create LLM client using the existing UnstractLLMClient
            llm_client = UnstractLLMClient(llm_adapter_instance)

            # Initialize services
            cache = LLMResponseCache()
            merger = EnrichmentMerger()

            # Create file storage client for reference data loading
            storage_client = FileStorageClient()
            ref_loader = ReferenceDataLoader(storage_client)

            # Create executor with wrapper for LLM client interface
            executor = LookUpExecutor(
                variable_resolver=VariableResolver,
                cache_manager=cache,
                reference_loader=ref_loader,
                llm_client=LLMClientWrapper(llm_client),
                org_id=organization_id,
            )

            # Create orchestrator with log emitter for WebSocket logs
            orchestrator = LookUpOrchestrator(
                executor=executor, merger=merger, log_emitter=log_emitter
            )

            # Handle prompt-level lookups if mapping is provided
            prompt_lookup_map = prompt_lookup_map or {}

            # Separate fields by their lookup assignment
            # Fields with specific lookups: only that lookup enriches them
            # Fields without specific lookups: all project-level lookups apply
            fields_with_specific_lookup: dict[str, dict[str, Any]] = {}
            fields_without_specific_lookup: dict[str, Any] = {}

            for field_name, field_value in input_data.items():
                if field_name in prompt_lookup_map:
                    lookup_id = prompt_lookup_map[field_name]
                    if lookup_id not in fields_with_specific_lookup:
                        fields_with_specific_lookup[lookup_id] = {}
                    fields_with_specific_lookup[lookup_id][field_name] = field_value
                else:
                    fields_without_specific_lookup[field_name] = field_value

            all_enrichment: dict[str, Any] = {}
            total_executed = 0
            total_successful = 0

            # Execute specific lookups for their assigned fields
            for lookup_id, fields in fields_with_specific_lookup.items():
                specific_project = next(
                    (p for p in lookup_projects if str(p.id) == lookup_id), None
                )
                if specific_project:
                    logger.info(
                        f"Executing prompt-level lookup {specific_project.name} "
                        f"for fields: {list(fields.keys())}"
                    )
                    result = orchestrator.execute_lookups(
                        input_data=fields,
                        lookup_projects=[specific_project],
                        execution_id=execution_id,
                        prompt_studio_project_id=prompt_studio_project_id,
                    )
                    all_enrichment.update(result.get("lookup_enrichment", {}))
                    metadata = result.get("_lookup_metadata", {})
                    total_executed += metadata.get("lookups_executed", 0)
                    total_successful += metadata.get("lookups_successful", 0)
                else:
                    logger.warning(
                        f"Lookup project {lookup_id} not found in linked projects "
                        f"for fields: {list(fields.keys())}"
                    )

            # Execute all project-level lookups for remaining fields
            if fields_without_specific_lookup:
                logger.info(
                    f"Executing project-level lookups for fields: "
                    f"{list(fields_without_specific_lookup.keys())}"
                )
                result = orchestrator.execute_lookups(
                    input_data=fields_without_specific_lookup,
                    lookup_projects=lookup_projects,
                    execution_id=execution_id,
                    prompt_studio_project_id=prompt_studio_project_id,
                )
                all_enrichment.update(result.get("lookup_enrichment", {}))
                metadata = result.get("_lookup_metadata", {})
                total_executed += metadata.get("lookups_executed", 0)
                total_successful += metadata.get("lookups_successful", 0)

            return {
                "lookup_enrichment": all_enrichment,
                "_lookup_metadata": {
                    "status": "success",
                    "lookups_executed": total_executed,
                    "lookups_successful": total_successful,
                    "prompt_level_lookups": len(fields_with_specific_lookup),
                    "project_level_fields": len(fields_without_specific_lookup),
                },
            }

        except Exception as e:
            logger.error(f"Error in lookup orchestrator: {e}", exc_info=True)
            return {
                "lookup_enrichment": {},
                "_lookup_metadata": {
                    "status": "error",
                    "message": str(e),
                    "lookups_executed": 0,
                    "lookups_successful": 0,
                },
            }


class LLMClientWrapper:
    """Wrapper to adapt UnstractLLMClient to LookUpExecutor interface.

    The LookUpExecutor expects an LLM client with a `generate(prompt, config)`
    method that returns a string.
    """

    def __init__(self, unstract_client: Any) -> None:
        """Initialize wrapper.

        Args:
            unstract_client: UnstractLLMClient instance
        """
        self.client = unstract_client

    def generate(self, prompt: str, config: dict[str, Any] | None = None) -> str:
        """Execute LLM generation.

        Args:
            prompt: The prompt to send to LLM
            config: Optional LLM configuration

        Returns:
            LLM response text
        """
        try:
            # Use the generate method from UnstractLLMClient
            response = self.client.generate(prompt=prompt, config=config or {})
            return response
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise
