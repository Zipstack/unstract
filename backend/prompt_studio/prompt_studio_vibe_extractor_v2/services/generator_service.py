"""Generator Service Integration.

This module integrates with the prompt service to generate
document extraction components.
"""

import asyncio
import logging
from typing import Any

from adapter_processor_v2.models import AdapterInstance
from platform_settings_v2.models import PlatformSettings
from utils.user_context import UserContext

from prompt_studio.prompt_studio_vibe_extractor_v2.models import (
    VibeExtractorProject,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.services.adapter_helper import (
    AdapterHelper,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.vibe_extractor_helper import (
    VibeExtractorHelper,
)

logger = logging.getLogger(__name__)


class GeneratorService:
    """Service to integrate with prompt service for generation."""

    @staticmethod
    def _get_system_llm_adapter() -> AdapterInstance:
        """Get system LLM adapter from platform settings.

        Returns:
            AdapterInstance configured as system LLM

        Raises:
            ValueError: If system LLM is not configured
        """
        try:
            organization = UserContext.get_organization()
            platform_settings = PlatformSettings.get_for_organization(organization)

            if not platform_settings.system_llm_adapter:
                raise ValueError(
                    "No system LLM adapter configured for this organization. "
                    "Please configure a system LLM in platform settings."
                )

            # Validate the adapter
            is_valid, error_msg = AdapterHelper.validate_llm_adapter(
                platform_settings.system_llm_adapter
            )
            if not is_valid:
                raise ValueError(f"System LLM adapter is invalid: {error_msg}")

            return platform_settings.system_llm_adapter

        except Exception as e:
            logger.error("Failed to get system LLM adapter: %s", str(e))
            raise ValueError(f"Failed to get system LLM adapter: {str(e)}") from e

    @staticmethod
    def _get_llm_config(
        project: VibeExtractorProject = None,
    ) -> dict[str, Any]:
        """Get LLM configuration from platform system LLM or project.

        Args:
            project: Optional VibeExtractorProject to get LLM from

        Returns:
            LLM configuration dictionary

        Raises:
            ValueError: If LLM configuration is missing or invalid
        """
        # If project has an LLM adapter, use it
        if project and project.llm_adapter:
            adapter = project.llm_adapter
        else:
            # Otherwise, get system LLM from platform settings
            adapter = GeneratorService._get_system_llm_adapter()

        # Convert adapter to LLM config
        try:
            llm_config = AdapterHelper.convert_to_llm_config(adapter)
            logger.info(
                "Using LLM adapter: %s (model: %s)",
                adapter.adapter_name,
                llm_config.get("model"),
            )
            return llm_config
        except Exception as e:
            error_msg = f"Failed to convert adapter to LLM config: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    @staticmethod
    def _get_reference_template() -> str:
        """Get reference metadata.yaml template.

        Returns:
            Reference template content
        """
        try:
            reference_template = VibeExtractorHelper.get_reference_template(
                "metadata.yaml"
            )
            return reference_template
        except Exception as e:
            logger.warning(f"Could not load reference template: {e}")
            # Return default template
            return """---
name_identifier: example
name: Example Document
description: |
  Example document description.
description_seo: |
  SEO optimized description.
html_meta_description: |
  HTML meta description.
tags:
  - example
version: 1.0.0
status: beta
visibility: public
author: Zipstack Inc
release_date: 2025-07-01
price_multiplier: 1.0
llm_model: claude-sonnet-1-7
extraction_features:
  locate_pages: true
  rolling_window: false
  challenge: false
"""

    @staticmethod
    def _create_progress_callback(project: VibeExtractorProject):
        """Create a progress callback for updating project status.

        Args:
            project: VibeExtractorProject instance

        Returns:
            Callback function
        """

        def progress_callback(step: str, status: str, message: str = ""):
            """Update project progress.

            Args:
                step: Generation step name
                status: Status (in_progress, completed, failed)
                message: Optional message
            """
            try:
                VibeExtractorHelper.update_generation_progress(
                    project, step, status, message
                )

                # Update project status based on step
                if status == "failed":
                    project.status = VibeExtractorProject.Status.FAILED
                    project.error_message = message
                    project.save(update_fields=["status", "error_message", "modified_at"])
                elif step == "generating_metadata":
                    project.status = VibeExtractorProject.Status.GENERATING_METADATA
                    project.save(update_fields=["status", "modified_at"])
                elif step == "generating_extraction_fields":
                    project.status = VibeExtractorProject.Status.GENERATING_FIELDS
                    project.save(update_fields=["status", "modified_at"])
                elif step == "generating_page_prompts" or step.startswith("generating_"):
                    project.status = VibeExtractorProject.Status.GENERATING_PROMPTS
                    project.save(update_fields=["status", "modified_at"])

            except Exception as e:
                logger.error(f"Error in progress callback: {e}")

        return progress_callback

    @staticmethod
    async def generate_all_async(
        project: VibeExtractorProject,
    ) -> dict[str, Any]:
        """Generate all components for a project asynchronously.

        Args:
            project: VibeExtractorProject instance

        Returns:
            Dictionary containing generation result
        """
        try:
            # Import here to avoid circular imports and ensure prompt service is available
            from unstract.prompt_service.services.vibe_extractor.api_helper import (
                generate_document_extraction_components_sync,
            )

            # Get system LLM adapter if not already set on project
            if not project.llm_adapter:
                system_llm = GeneratorService._get_system_llm_adapter()
                project.llm_adapter = system_llm
                project.save(update_fields=["llm_adapter"])

            # Get LLM configuration
            llm_config = GeneratorService._get_llm_config(project)

            # Get reference template
            reference_template = GeneratorService._get_reference_template()

            # Get output directory
            output_dir = VibeExtractorHelper.get_project_output_path(project)

            # Create progress callback
            progress_callback = GeneratorService._create_progress_callback(project)

            # Generate all components
            result = generate_document_extraction_components_sync(
                doc_type=project.document_type,
                output_dir=str(output_dir.parent),
                llm_config=llm_config,
                reference_template=reference_template,
                progress_callback=progress_callback,
            )

            # Update project status based on result
            if result["status"] == "success":
                project.status = VibeExtractorProject.Status.COMPLETED
                project.generation_output_path = result["output_path"]
                project.error_message = ""
                project.save(
                    update_fields=[
                        "status",
                        "generation_output_path",
                        "error_message",
                        "modified_at",
                    ]
                )
            else:
                project.status = VibeExtractorProject.Status.FAILED
                project.error_message = result.get("error", "Unknown error")
                project.save(update_fields=["status", "error_message", "modified_at"])

            return result

        except Exception as e:
            error_msg = f"Error during generation: {str(e)}"
            logger.error(error_msg, exc_info=True)

            project.status = VibeExtractorProject.Status.FAILED
            project.error_message = error_msg
            project.save(update_fields=["status", "error_message", "modified_at"])

            return {"status": "error", "error": error_msg}

    @staticmethod
    def generate_all(project: VibeExtractorProject) -> dict[str, Any]:
        """Generate all components for a project (sync wrapper).

        Args:
            project: VibeExtractorProject instance

        Returns:
            Dictionary containing generation result
        """
        # Run the async function in a new event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(GeneratorService.generate_all_async(project))
