"""Service layer for AgenticProject operations."""

import logging
from typing import Dict, List, Optional
from uuid import UUID

from prompt_studio.agentic_studio_v2.models import AgenticProject
from prompt_studio.prompt_studio_core_v2.models import CustomTool

logger = logging.getLogger(__name__)


class AgenticProjectService:
    """Business logic for managing Agentic Projects."""

    @staticmethod
    def create_agentic_project(
        custom_tool_id: UUID,
        name: str,
        description: str = "",
        organization=None,
        created_by=None,
        **llm_settings,
    ) -> AgenticProject:
        """Create a new agentic project linked to a CustomTool.

        Args:
            custom_tool_id: UUID of the parent CustomTool
            name: Project name
            description: Optional description
            organization: Organization instance
            created_by: User who created the project
            **llm_settings: Optional LLM adapter instances
                - extractor_llm: AdapterInstance for extraction
                - agent_llm: AdapterInstance for agents
                - llmwhisperer: AdapterInstance for text extraction
                - lightweight_llm: AdapterInstance for lightweight tasks

        Returns:
            AgenticProject: Created project instance
        """
        try:
            custom_tool = CustomTool.objects.get(id=custom_tool_id)
        except CustomTool.DoesNotExist:
            raise ValueError(f"CustomTool with id {custom_tool_id} not found")

        project = AgenticProject.objects.create(
            custom_tool=custom_tool,
            name=name,
            description=description,
            organization=organization,
            created_by=created_by,
            extractor_llm=llm_settings.get("extractor_llm"),
            agent_llm=llm_settings.get("agent_llm"),
            llmwhisperer=llm_settings.get("llmwhisperer"),
            lightweight_llm=llm_settings.get("lightweight_llm"),
        )

        logger.info(f"Created AgenticProject: {project.id} - {project.name}")
        return project

    @staticmethod
    def get_project_with_settings(project_id: UUID) -> Optional[AgenticProject]:
        """Fetch project with all related LLM configurations.

        Args:
            project_id: UUID of the project

        Returns:
            AgenticProject with prefetched relations or None
        """
        try:
            return AgenticProject.objects.select_related(
                "custom_tool",
                "extractor_llm",
                "agent_llm",
                "llmwhisperer",
                "lightweight_llm",
                "created_by",
            ).get(id=project_id)
        except AgenticProject.DoesNotExist:
            return None

    @staticmethod
    def update_llm_settings(
        project_id: UUID, **llm_settings
    ) -> Optional[AgenticProject]:
        """Update LLM adapter settings for a project.

        Args:
            project_id: UUID of the project
            **llm_settings: LLM adapter instances to update

        Returns:
            Updated AgenticProject or None
        """
        project = AgenticProjectService.get_project_with_settings(project_id)
        if not project:
            return None

        if "extractor_llm" in llm_settings:
            project.extractor_llm = llm_settings["extractor_llm"]
        if "agent_llm" in llm_settings:
            project.agent_llm = llm_settings["agent_llm"]
        if "llmwhisperer" in llm_settings:
            project.llmwhisperer = llm_settings["llmwhisperer"]
        if "lightweight_llm" in llm_settings:
            project.lightweight_llm = llm_settings["lightweight_llm"]

        project.save()
        logger.info(f"Updated LLM settings for project {project_id}")
        return project

    @staticmethod
    def set_canary_fields(project_id: UUID, field_paths: List[str]) -> bool:
        """Set canary fields for regression testing during tuning.

        Args:
            project_id: UUID of the project
            field_paths: List of field paths to protect (e.g., ['invoice_number', 'total'])

        Returns:
            bool: True if successful
        """
        project = AgenticProjectService.get_project_with_settings(project_id)
        if not project:
            return False

        project.canary_fields = field_paths
        project.save()
        logger.info(f"Set {len(field_paths)} canary fields for project {project_id}")
        return True

    @staticmethod
    def mark_wizard_complete(project_id: UUID) -> bool:
        """Mark the agentic wizard as completed.

        Args:
            project_id: UUID of the project

        Returns:
            bool: True if successful
        """
        project = AgenticProjectService.get_project_with_settings(project_id)
        if not project:
            return False

        project.wizard_completed = True
        project.save()
        logger.info(f"Marked wizard complete for project {project_id}")
        return True

    @staticmethod
    def get_project_stats(project_id: UUID) -> Optional[Dict]:
        """Get statistics for a project.

        Args:
            project_id: UUID of the project

        Returns:
            Dict with project statistics or None
        """
        project = AgenticProjectService.get_project_with_settings(project_id)
        if not project:
            return None

        document_count = project.documents.count()
        verified_count = project.verified_data.count()
        schema_count = project.schemas.count()
        prompt_count = project.prompt_versions.count()

        active_prompt = project.prompt_versions.filter(is_active=True).first()

        return {
            "project_id": str(project.id),
            "project_name": project.name,
            "document_count": document_count,
            "verified_count": verified_count,
            "schema_count": schema_count,
            "prompt_count": prompt_count,
            "active_prompt_version": active_prompt.version if active_prompt else None,
            "active_prompt_accuracy": active_prompt.accuracy if active_prompt else None,
            "wizard_completed": project.wizard_completed,
        }
