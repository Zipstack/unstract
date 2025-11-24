"""Extraction service for running provisional extraction with LLM.

Based on AutoPrompt's extraction_service.py pattern.
"""

import json
import logging
from typing import Any, Dict, Optional

from adapter_processor_v2.models import AdapterInstance
from django.conf import settings

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service for running extraction directly with LLM adapter.

    This follows AutoPrompt's pattern of running extraction locally
    rather than calling an external service.
    """

    @staticmethod
    def run_provisional_extraction(
        prompt_text: str,
        document_text: str,
        schema_data: Optional[Dict[str, Any]],
        llm_adapter_id: str,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Run a provisional extraction on a document.

        This generates initial extracted data that can be reviewed and saved
        as verified data.

        Args:
            prompt_text: The extraction prompt text
            document_text: The document raw text to extract from
            schema_data: Optional JSON schema
            llm_adapter_id: UUID of the LLM adapter to use
            organization_id: Organization ID for the request

        Returns:
            Extracted JSON data (dict)

        Raises:
            ValueError: If prerequisites not met
            RuntimeError: If extraction fails
        """
        if not prompt_text:
            raise ValueError("Prompt text is required")

        if not document_text:
            raise ValueError("Document text is required")

        if not llm_adapter_id:
            raise ValueError("LLM adapter ID is required")

        # Build final prompt with document text
        if "{{DOCUMENT_TEXT}}" in prompt_text:
            # Replace placeholder with actual document text
            final_prompt = prompt_text.replace("{{DOCUMENT_TEXT}}", document_text)
            logger.info("Replaced {{DOCUMENT_TEXT}} placeholder in prompt")
        else:
            # Append document text to prompt
            final_prompt = f"{prompt_text}\n\n# Document\n\n{document_text}"
            logger.info("Appended document text to prompt")

        logger.info(f"Running provisional extraction with LLM adapter {llm_adapter_id}")

        try:
            # Use SDK1 LLM for extraction (same as AutoPrompt pattern)
            from unstract.sdk1.llm import LLM

            # Create LLM instance
            llm = LLM(
                adapter_instance_id=llm_adapter_id,
            )

            # Call LLM for completion
            logger.info("Calling LLM for extraction...")
            response_text = llm.complete(prompt=final_prompt)

            logger.info(f"LLM response received, length: {len(response_text)}")

            # Parse JSON from response
            extracted_data = ExtractionService._parse_json_response(response_text)

            logger.info(
                f"Successfully extracted data with {len(extracted_data)} top-level fields"
            )
            return extracted_data

        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Extraction failed: {str(e)}") from e

    @staticmethod
    def _parse_json_response(response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response text.

        Handles cases where LLM wraps JSON in markdown code blocks.

        Args:
            response_text: Raw response text from LLM

        Returns:
            Parsed JSON as dict

        Raises:
            ValueError: If JSON parsing fails
        """
        # Try to extract JSON from markdown code blocks
        import re

        # Remove markdown code block markers if present
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object in response
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_text.strip()

        # Parse JSON
        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                raise ValueError("Response must be a JSON object")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Response text: {response_text[:500]}")

            # Try json_repair as fallback
            try:
                import json_repair

                data = json_repair.loads(json_str)
                logger.info("Successfully repaired malformed JSON")
                return data
            except Exception as repair_error:
                logger.error(f"JSON repair also failed: {repair_error}")
                raise ValueError(
                    f"Failed to parse JSON response: {str(e)}"
                ) from e
