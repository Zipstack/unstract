"""HTTP client for communicating with prompt-service agentic endpoints."""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class PromptServiceClient:
    """Client for making requests to prompt-service agentic endpoints.

    The prompt-service hosts:
    - LLM bridge (UnstractAutogenBridge)
    - AutoGen agents (Summarizer, Uniformer, Finalizer, PromptArchitect, Tuners)
    - Agent orchestration logic
    """

    def __init__(self, organization_id: str, timeout: int = 300):
        """Initialize client with organization context.

        Args:
            organization_id: Organization ID for usage tracking
            timeout: Request timeout in seconds (default 5 minutes for agent operations)
        """
        self.base_url = f"{settings.PROMPT_HOST}:{settings.PROMPT_PORT}"
        self.organization_id = organization_id
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def summarize_document(
        self, document_id: UUID, project_id: UUID, document_text: str
    ) -> Optional[Dict[str, Any]]:
        """Summarize a document to extract field candidates.

        Args:
            document_id: UUID of the document
            project_id: UUID of the project
            document_text: Raw text from LLMWhisperer

        Returns:
            Dict with summary text or None on error
        """
        endpoint = f"{self.base_url}/agentic/summarize"
        payload = {
            "document_id": str(document_id),
            "project_id": str(project_id),
            "document_text": document_text,
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Summarization failed: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Summarization request failed: {e}")
            return None

    async def uniformize_schemas(
        self, project_id: UUID, summaries: List[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """Uniformize multiple document schemas into a consistent structure.

        Args:
            project_id: UUID of the project
            summaries: List of document summaries with field candidates

        Returns:
            Dict with uniformized schema or None on error
        """
        endpoint = f"{self.base_url}/agentic/uniformize"
        payload = {
            "project_id": str(project_id),
            "summaries": summaries,
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Schema uniformization failed: {e}")
            return None

    async def finalize_schema(
        self, project_id: UUID, uniform_schema: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Finalize schema into valid JSON Schema format.

        Args:
            project_id: UUID of the project
            uniform_schema: Uniformized schema from uniformize step

        Returns:
            Dict with final JSON Schema or None on error
        """
        endpoint = f"{self.base_url}/agentic/finalize"
        payload = {
            "project_id": str(project_id),
            "uniform_schema": uniform_schema,
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Schema finalization failed: {e}")
            return None

    async def generate_prompt(
        self, project_id: UUID, schema: Dict[str, Any], examples: Optional[List[Dict]] = None
    ) -> Optional[Dict[str, Any]]:
        """Generate initial extraction prompt from schema.

        Args:
            project_id: UUID of the project
            schema: JSON schema for extraction
            examples: Optional example documents

        Returns:
            Dict with generated prompt or None on error
        """
        endpoint = f"{self.base_url}/agentic/generate-prompt"
        payload = {
            "project_id": str(project_id),
            "schema": schema,
            "examples": examples or [],
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Prompt generation failed: {e}")
            return None

    async def extract_from_document(
        self,
        document_id: UUID,
        project_id: UUID,
        prompt_text: str,
        document_text: str,
        schema: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Extract data from document using a prompt.

        Args:
            document_id: UUID of the document
            project_id: UUID of the project
            prompt_text: Extraction prompt
            document_text: Document text
            schema: Expected schema

        Returns:
            Dict with extracted data or None on error
        """
        endpoint = f"{self.base_url}/agentic/extract"
        payload = {
            "document_id": str(document_id),
            "project_id": str(project_id),
            "prompt_text": prompt_text,
            "document_text": document_text,
            "schema": schema,
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return None

    async def compare_extracted_to_verified(
        self,
        project_id: UUID,
        extracted_data: Dict[str, Any],
        verified_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Compare extracted data to verified ground truth.

        Args:
            project_id: UUID of the project
            extracted_data: Data extracted by LLM
            verified_data: Ground truth data

        Returns:
            Dict with comparison results (field-level matches and error types) or None
        """
        endpoint = f"{self.base_url}/agentic/compare"
        payload = {
            "project_id": str(project_id),
            "extracted_data": extracted_data,
            "verified_data": verified_data,
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Comparison failed: {e}")
            return None

    async def tune_field(
        self,
        project_id: UUID,
        field_path: str,
        current_prompt: str,
        schema: Dict[str, Any],
        failures: List[Dict[str, Any]],
        canary_fields: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Tune extraction prompt for a specific failing field.

        Args:
            project_id: UUID of the project
            field_path: Dot-separated field path (e.g., 'customer.name')
            current_prompt: Current extraction prompt
            schema: JSON schema
            failures: List of failure cases with extracted vs verified values
            canary_fields: Optional list of fields to protect from regression

        Returns:
            Dict with tuned prompt or None on error
        """
        endpoint = f"{self.base_url}/agentic/tune-field"
        payload = {
            "project_id": str(project_id),
            "field_path": field_path,
            "current_prompt": current_prompt,
            "schema": schema,
            "failures": failures,
            "canary_fields": canary_fields or [],
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Field tuning failed: {e}")
            return None

    async def run_full_pipeline(self, project_id: UUID) -> Optional[Dict[str, Any]]:
        """Run the full agentic pipeline (summarize → schema → prompt).

        Args:
            project_id: UUID of the project

        Returns:
            Dict with pipeline result or None on error
        """
        endpoint = f"{self.base_url}/agentic/run-pipeline"
        payload = {
            "project_id": str(project_id),
            "organization_id": self.organization_id,
        }

        try:
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            return None

    async def close(self):
        """Close the HTTP client connection."""
        await self.client.aclose()
