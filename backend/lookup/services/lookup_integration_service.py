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
    ) -> dict[str, Any]:
        """Execute Lookup enrichment if PS project has linked Lookups.

        Features:
        - Zero overhead if no links exist
        - Timeout protection to not block extraction
        - Graceful degradation on errors
        - Full audit logging

        Args:
            prompt_studio_project_id: UUID of Prompt Studio project
            extracted_data: Dict of extracted field values
            run_id: Optional execution run ID for tracking
            timeout: Max seconds to wait (default from settings)

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

        try:
            return LookupIntegrationService._execute_enrichment(
                prompt_studio_project_id=prompt_studio_project_id,
                extracted_data=extracted_data,
                run_id=run_id,
                timeout=timeout,
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
    ) -> dict[str, Any]:
        """Internal method to execute enrichment with timeout."""
        from lookup.models import PromptStudioLookupLink

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

        # Execute with timeout protection
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                LookupIntegrationService._run_orchestrator,
                lookup_projects=lookup_projects,
                input_data=extracted_data,
                execution_id=run_id or str(uuid.uuid4()),
                prompt_studio_project_id=prompt_studio_project_id,
            )
            result = future.result(timeout=timeout)

        return result

    @staticmethod
    def _run_orchestrator(
        lookup_projects: list,
        input_data: dict[str, Any],
        execution_id: str,
        prompt_studio_project_id: str,
    ) -> dict[str, Any]:
        """Execute the lookup orchestrator for all linked projects."""
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
            )

            # Create orchestrator
            orchestrator = LookUpOrchestrator(executor=executor, merger=merger)

            # Execute lookups with audit context
            result = orchestrator.execute_lookups(
                input_data=input_data,
                lookup_projects=lookup_projects,
                execution_id=execution_id,
                prompt_studio_project_id=prompt_studio_project_id,
            )

            return {
                "lookup_enrichment": result.get("lookup_enrichment", {}),
                "_lookup_metadata": result.get("_lookup_metadata", {}),
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
