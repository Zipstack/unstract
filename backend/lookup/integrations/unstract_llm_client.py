"""Unstract LLM Client for Look-Up enrichment.

This module provides integration with Unstract's LLM abstraction
using the SDK's LLM class for generating enrichment data.
"""

import json
import logging
from typing import Any, Protocol

from adapter_processor_v2.models import AdapterInstance
from litellm import get_max_tokens, token_counter

from lookup.exceptions import ContextWindowExceededError
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters
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

    # Reserve tokens for LLM response output
    RESERVED_OUTPUT_TOKENS = 2048
    # Default context window if we can't determine the model's limit
    DEFAULT_CONTEXT_WINDOW = 4096

    def __init__(self, adapter_instance: AdapterInstance):
        """Initialize the LLM client with an adapter instance.

        Args:
            adapter_instance: The AdapterInstance model object containing
                             the LLM configuration
        """
        self.adapter_instance = adapter_instance
        self.adapter_id = adapter_instance.adapter_id
        self.adapter_metadata = adapter_instance.metadata  # Decrypted metadata

        # Initialize model info for context validation
        self._model_name = self._get_model_name()
        self._context_limit = self._get_context_limit()

    def _get_model_name(self) -> str:
        """Get the model name from adapter metadata.

        Returns:
            The model name string used by litellm
        """
        try:
            adapter = adapters[self.adapter_id][Common.MODULE]
            return adapter.validate_model(self.adapter_metadata)
        except Exception as e:
            logger.warning(f"Failed to get model name: {e}")
            return "unknown"

    def _get_context_limit(self) -> int:
        """Get context window limit for the configured LLM.

        Returns:
            Maximum number of tokens the model can handle
        """
        try:
            return get_max_tokens(self._model_name)
        except Exception as e:
            logger.warning(
                f"Failed to get context limit for {self._model_name}: {e}. "
                f"Using default: {self.DEFAULT_CONTEXT_WINDOW}"
            )
            return self.DEFAULT_CONTEXT_WINDOW

    def validate_context_size(self, prompt: str) -> None:
        """Validate that the prompt fits within the LLM's context window.

        This method counts the tokens in the prompt and compares against
        the model's context window limit, accounting for reserved output tokens.

        Args:
            prompt: The complete prompt to send to the LLM

        Raises:
            ContextWindowExceededError: If the prompt exceeds the context limit
        """
        try:
            # Count tokens using litellm's accurate counter
            messages = [{"role": "user", "content": prompt}]
            token_count = token_counter(model=self._model_name, messages=messages)
        except Exception as e:
            # Fallback to rough estimation if token counting fails
            logger.warning(f"Token counting failed, using estimation: {e}")
            token_count = len(prompt) // 4  # Rough estimate: ~4 chars per token

        # Account for reserved output tokens
        available_tokens = self._context_limit - self.RESERVED_OUTPUT_TOKENS

        logger.debug(
            f"Context validation: {token_count:,} tokens in prompt, "
            f"{available_tokens:,} available (limit: {self._context_limit:,}, "
            f"reserved: {self.RESERVED_OUTPUT_TOKENS})"
        )

        if token_count > available_tokens:
            raise ContextWindowExceededError(
                token_count=token_count,
                context_limit=available_tokens,
                model=self._model_name,
            )

    def generate(self, prompt: str, config: dict[str, Any], timeout: int = 30) -> str:
        """Generate LLM response for Look-Up enrichment.

        Args:
            prompt: The prompt text with resolved variables and reference data
            config: Additional LLM configuration (temperature, etc.)
            timeout: Request timeout in seconds

        Returns:
            JSON-formatted string with enrichment data

        Raises:
            ContextWindowExceededError: If prompt exceeds context window
            RuntimeError: If LLM call fails
        """
        # Validate context size before calling LLM
        self.validate_context_size(prompt)

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
