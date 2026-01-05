"""Unstract LLM Client for Look-Up enrichment.

This module provides integration with Unstract's LLM abstraction
using the SDK's LLM class for generating enrichment data.
"""

import json
import logging
from typing import Any, Protocol

from adapter_processor_v2.models import AdapterInstance

from unstract.sdk1.llm import LLM

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM client abstraction."""

    def generate(self, prompt: str, config: dict[str, Any]) -> str:
        """Generate LLM response for the prompt."""
        ...


class UnstractLLMClient(LLMClient):
    """LLM client implementation using Unstract's SDK LLM class.

    This client uses the actual LLM adapters configured in the platform
    to generate enrichment data for Look-Ups.
    """

    def __init__(self, adapter_instance: AdapterInstance):
        """Initialize the LLM client with an adapter instance.

        Args:
            adapter_instance: The AdapterInstance model object containing
                             the LLM configuration
        """
        self.adapter_instance = adapter_instance
        self.adapter_id = adapter_instance.adapter_id
        self.adapter_metadata = adapter_instance.metadata  # Decrypted metadata

    def generate(self, prompt: str, config: dict[str, Any], timeout: int = 30) -> str:
        """Generate LLM response for Look-Up enrichment.

        Args:
            prompt: The prompt text with resolved variables and reference data
            config: Additional LLM configuration (temperature, etc.)
            timeout: Request timeout in seconds

        Returns:
            JSON-formatted string with enrichment data

        Raises:
            RuntimeError: If LLM call fails
        """
        try:
            # Create LLM instance using SDK
            llm = LLM(adapter_id=self.adapter_id, adapter_metadata=self.adapter_metadata)

            # Call the LLM
            logger.debug(f"Calling LLM with prompt length: {len(prompt)}")
            response = llm.complete(prompt)

            # Extract the response text
            response_text = response["response"].text

            logger.debug(f"LLM response: {response_text[:500]}...")

            # Validate it's valid JSON
            try:
                json.loads(response_text)
                return response_text
            except json.JSONDecodeError:
                # Try to extract JSON from response
                return self._extract_json(response_text)

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise RuntimeError(f"LLM generation failed: {str(e)}")

    def _extract_json(self, response: str) -> str:
        """Extract JSON from LLM response if wrapped in text.

        Args:
            response: Raw LLM response

        Returns:
            Extracted JSON string
        """
        # Look for JSON object pattern (handles nested objects)
        # Try to find content between first { and last }
        start_idx = response.find("{")
        end_idx = response.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            potential_json = response[start_idx : end_idx + 1]
            try:
                json.loads(potential_json)
                return potential_json
            except json.JSONDecodeError:
                pass

        # If no valid JSON found, create a basic response
        logger.warning(f"Could not extract JSON from response: {response[:200]}")
        return json.dumps(
            {
                "raw_response": response[:500],
                "confidence": 0.3,
                "warning": "Could not extract structured data from LLM response",
            }
        )
