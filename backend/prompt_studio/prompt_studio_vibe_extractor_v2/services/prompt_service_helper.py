"""Helper to communicate with prompt-service for vibe extractor operations.

This module provides a helper class that uses the SDK's PromptTool
to communicate with the prompt-service, following Unstract's standards.
"""

import logging
from typing import Any, Dict

from account_v2.constants import Common
from django.conf import settings
from utils.local_context import StateStore

from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import (
    PromptIdeBaseTool,
)
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.prompt import PromptTool
    from unstract.sdk1.constants import LogLevel
else:
    from unstract.sdk.prompt import PromptTool
    from unstract.sdk.constants import LogLevel

logger = logging.getLogger(__name__)


class VibeExtractorPromptServiceHelper:
    """Helper class to communicate with prompt-service for vibe extractor.

    This class follows Unstract's standard pattern of using PromptIdeBaseTool
    with the SDK's PromptTool to make HTTP calls to the prompt-service.
    """

    @staticmethod
    def _get_prompt_tool(org_id: str) -> PromptTool:
        """Get configured PromptTool instance.

        Args:
            org_id: Organization ID

        Returns:
            Configured PromptTool instance
        """
        # Create PromptIdeBaseTool (standard tool used in backend)
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        # Create PromptTool instance
        prompt_tool = PromptTool(
            tool=util,
            prompt_host=settings.PROMPT_HOST,
            prompt_port=settings.PROMPT_PORT,
            request_id=StateStore.get(Common.REQUEST_ID),
        )

        return prompt_tool

    @staticmethod
    def guess_document_type(
        file_content: str,
        llm_config: Dict[str, Any],
        org_id: str,
    ) -> Dict[str, Any]:
        """Guess document type from file content.

        Args:
            file_content: Extracted text content from document
            llm_config: LLM configuration dictionary
            org_id: Organization ID

        Returns:
            Dictionary with status, document_type, confidence, etc.
        """
        prompt_tool = VibeExtractorPromptServiceHelper._get_prompt_tool(org_id)

        payload = {
            "file_content": file_content,
            "llm_config": llm_config,
        }

        return prompt_tool.guess_document_type(payload=payload)

    @staticmethod
    def generate_metadata(
        doc_type: str,
        llm_config: Dict[str, Any],
        reference_template: str,
        org_id: str,
    ) -> Dict[str, Any]:
        """Generate metadata for a document type.

        Args:
            doc_type: Document type name
            llm_config: LLM configuration dictionary
            reference_template: Reference metadata template
            org_id: Organization ID

        Returns:
            Dictionary with status and metadata
        """
        prompt_tool = VibeExtractorPromptServiceHelper._get_prompt_tool(org_id)

        payload = {
            "doc_type": doc_type,
            "llm_config": llm_config,
            "reference_template": reference_template,
        }

        return prompt_tool.generate_metadata(payload=payload)

    @staticmethod
    def generate_extraction_fields(
        doc_type: str,
        metadata_description: str,
        llm_config: Dict[str, Any],
        org_id: str,
    ) -> Dict[str, Any]:
        """Generate extraction fields YAML.

        Args:
            doc_type: Document type name
            metadata_description: Description from metadata
            llm_config: LLM configuration dictionary
            org_id: Organization ID

        Returns:
            Dictionary with status and extraction_yaml
        """
        prompt_tool = VibeExtractorPromptServiceHelper._get_prompt_tool(org_id)

        payload = {
            "doc_type": doc_type,
            "metadata_description": metadata_description,
            "llm_config": llm_config,
        }

        return prompt_tool.generate_extraction_fields(payload=payload)

    @staticmethod
    def generate_page_prompts(
        doc_type: str,
        metadata_description: str,
        llm_config: Dict[str, Any],
        org_id: str,
    ) -> Dict[str, Any]:
        """Generate page extraction prompts.

        Args:
            doc_type: Document type name
            metadata_description: Description from metadata
            llm_config: LLM configuration dictionary
            org_id: Organization ID

        Returns:
            Dictionary with status, system_prompt, user_prompt
        """
        prompt_tool = VibeExtractorPromptServiceHelper._get_prompt_tool(org_id)

        payload = {
            "doc_type": doc_type,
            "metadata_description": metadata_description,
            "llm_config": llm_config,
        }

        return prompt_tool.generate_page_prompts(payload=payload)

    @staticmethod
    def generate_scalar_prompts(
        doc_type: str,
        metadata_description: str,
        extraction_yaml: str,
        scalar_fields: list,
        llm_config: Dict[str, Any],
        org_id: str,
    ) -> Dict[str, Any]:
        """Generate scalar extraction prompts.

        Args:
            doc_type: Document type name
            metadata_description: Description from metadata
            extraction_yaml: Extraction YAML string
            scalar_fields: List of scalar field names
            llm_config: LLM configuration dictionary
            org_id: Organization ID

        Returns:
            Dictionary with status, system_prompt, user_prompt
        """
        prompt_tool = VibeExtractorPromptServiceHelper._get_prompt_tool(org_id)

        payload = {
            "doc_type": doc_type,
            "metadata_description": metadata_description,
            "extraction_yaml": extraction_yaml,
            "scalar_fields": scalar_fields,
            "llm_config": llm_config,
        }

        return prompt_tool.generate_scalar_prompts(payload=payload)

    @staticmethod
    def generate_table_prompts(
        doc_type: str,
        metadata_description: str,
        extraction_yaml: str,
        list_fields: list,
        llm_config: Dict[str, Any],
        org_id: str,
    ) -> Dict[str, Any]:
        """Generate table extraction prompts.

        Args:
            doc_type: Document type name
            metadata_description: Description from metadata
            extraction_yaml: Extraction YAML string
            list_fields: List of list/table field names
            llm_config: LLM configuration dictionary
            org_id: Organization ID

        Returns:
            Dictionary with status, system_prompt, user_prompt
        """
        prompt_tool = VibeExtractorPromptServiceHelper._get_prompt_tool(org_id)

        payload = {
            "doc_type": doc_type,
            "metadata_description": metadata_description,
            "extraction_yaml": extraction_yaml,
            "list_fields": list_fields,
            "llm_config": llm_config,
        }

        return prompt_tool.generate_table_prompts(payload=payload)
