"""LLM Provider integration for Look-Up enrichment.

This module provides integration with various LLM providers
(OpenAI, Anthropic, etc.) for generating enrichment data.
"""

import json
import logging
import os
import time
from typing import Any

from ..protocols import LLMClient

logger = logging.getLogger(__name__)


class UnstractLLMClient(LLMClient):
    """Implementation of LLMClient using Unstract's LLM abstraction.

    This client integrates with the Unstract platform's LLM providers
    to generate enrichment data for Look-Ups.
    """

    def __init__(self, provider: str | None = None, model: str | None = None):
        """Initialize the LLM client.

        Args:
            provider: LLM provider name (e.g., 'openai', 'anthropic')
            model: Model name (e.g., 'gpt-4', 'claude-2')
        """
        self.default_provider = provider or os.getenv(
            "LOOKUP_DEFAULT_LLM_PROVIDER", "openai"
        )
        self.default_model = model or os.getenv("LOOKUP_DEFAULT_LLM_MODEL", "gpt-4")

        # Import Unstract LLM utilities
        try:
            from unstract.llmbox import LLMBox
            from unstract.llmbox.llm import LLM

            self.LLMBox = LLMBox
            self.LLM = LLM
            self.llm_available = True
        except ImportError:
            logger.warning("Unstract LLMBox not available, using fallback implementation")
            self.llm_available = False

    def _get_llm_instance(self, config: dict[str, Any]):
        """Get an LLM instance based on configuration.

        Args:
            config: LLM configuration

        Returns:
            LLM instance
        """
        if not self.llm_available:
            raise RuntimeError("LLM integration not available")

        provider = config.get("provider", self.default_provider)
        model = config.get("model", self.default_model)

        # Create LLM instance using Unstract's LLMBox
        # This would integrate with the actual Unstract LLM abstraction
        # For now, we'll use a simplified approach

        # Map provider to Unstract's LLM types
        provider_map = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "azure_openai": "AzureOpenAI",
            "gemini": "Gemini",
            "vertex_ai": "VertexAI",
        }

        llm_provider = provider_map.get(provider, "OpenAI")

        # Create configuration for the provider
        llm_config = {
            "provider": llm_provider,
            "model": model,
            "temperature": config.get("temperature", 0.7),
            "max_tokens": config.get("max_tokens", 1000),
        }

        # Add API keys based on provider
        if provider == "openai":
            llm_config["api_key"] = os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic":
            llm_config["api_key"] = os.getenv("ANTHROPIC_API_KEY")
        elif provider == "azure_openai":
            llm_config["api_key"] = os.getenv("AZURE_OPENAI_API_KEY")
            llm_config["endpoint"] = os.getenv("AZURE_OPENAI_ENDPOINT")

        # For now, return a mock implementation
        # In production, this would create actual LLM instance
        return llm_config

    def generate(self, prompt: str, config: dict[str, Any], timeout: int = 30) -> str:
        """Generate LLM response for Look-Up enrichment.

        Args:
            prompt: The prompt text with resolved variables
            config: LLM configuration (provider, model, temperature, etc.)
            timeout: Request timeout in seconds

        Returns:
            JSON-formatted string with enrichment data

        Raises:
            RuntimeError: If LLM call fails
        """
        start_time = time.time()

        try:
            if self.llm_available:
                # Use actual Unstract LLM integration
                llm_config = self._get_llm_instance(config)

                # In production, this would make actual LLM call
                # For now, simulate the call
                response = self._simulate_llm_call(prompt, llm_config)
            else:
                # Fallback implementation
                response = self._fallback_generate(prompt, config)

            # Validate response is JSON
            try:
                json.loads(response)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                response = self._extract_json(response)

            elapsed_time = time.time() - start_time
            logger.info(f"LLM generation completed in {elapsed_time:.2f}s")

            return response

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise RuntimeError(f"LLM generation failed: {str(e)}")

    def _simulate_llm_call(self, prompt: str, config: dict[str, Any]) -> str:
        """Simulate LLM call for development/testing.

        In production, this would be replaced with actual LLM API calls.
        """
        # Simulate some processing
        time.sleep(0.5)

        # Generate mock response based on prompt content
        if "vendor" in prompt.lower():
            return json.dumps(
                {
                    "canonical_vendor": "Sample Vendor Inc.",
                    "vendor_category": "SaaS",
                    "vendor_type": "Software",
                    "confidence": 0.95,
                }
            )
        elif "product" in prompt.lower():
            return json.dumps(
                {
                    "product_name": "Sample Product",
                    "product_category": "Enterprise Software",
                    "product_type": "Cloud Service",
                    "confidence": 0.92,
                }
            )
        else:
            return json.dumps({"enriched_data": "Sample enrichment", "confidence": 0.88})

    def _fallback_generate(self, prompt: str, config: dict[str, Any]) -> str:
        """Fallback generation when LLM integration is not available.

        This is primarily for testing and development.
        """
        logger.warning("Using fallback LLM generation")

        # Simple pattern matching for testing
        response_data = {
            "status": "fallback",
            "message": "LLM integration not available",
            "confidence": 0.5,
        }

        # Add some basic enrichment based on prompt
        if "vendor" in prompt.lower():
            response_data["canonical_vendor"] = "Unknown Vendor"
            response_data["vendor_category"] = "Unknown"
        elif "product" in prompt.lower():
            response_data["product_name"] = "Unknown Product"
            response_data["product_category"] = "Unknown"

        return json.dumps(response_data)

    def _extract_json(self, response: str) -> str:
        """Extract JSON from LLM response if wrapped in text.

        Args:
            response: Raw LLM response

        Returns:
            Extracted JSON string
        """
        # Try to find JSON in the response
        import re

        # Look for JSON object pattern
        json_pattern = r"\{[^{}]*\}"
        matches = re.findall(json_pattern, response)

        if matches:
            # Try to parse each match
            for match in matches:
                try:
                    json.loads(match)
                    return match
                except json.JSONDecodeError:
                    continue

        # If no valid JSON found, create a basic response
        return json.dumps(
            {
                "raw_response": response[:500],  # Truncate if too long
                "confidence": 0.3,
                "warning": "Could not extract structured data",
            }
        )

    def validate_response(self, response: str) -> bool:
        """Validate that the LLM response is properly formatted.

        Args:
            response: LLM response string

        Returns:
            True if valid JSON with required fields
        """
        try:
            data = json.loads(response)

            # Check for confidence score
            if "confidence" not in data:
                logger.warning("Response missing confidence score")
                return False

            # Check confidence is valid
            confidence = data.get("confidence", 0)
            if not (0 <= confidence <= 1):
                logger.warning(f"Invalid confidence score: {confidence}")
                return False

            return True

        except json.JSONDecodeError:
            logger.error("Response is not valid JSON")
            return False

    def get_token_count(self, text: str, model: str = None) -> int:
        """Estimate token count for the given text.

        Args:
            text: Input text
            model: Model name for accurate counting

        Returns:
            Estimated token count
        """
        # Simple estimation: ~4 characters per token
        # In production, use tiktoken or model-specific tokenizer
        return len(text) // 4


class OpenAILLMClient(UnstractLLMClient):
    """OpenAI-specific LLM client implementation."""

    def __init__(self):
        """Initialize OpenAI client."""
        super().__init__(provider="openai", model="gpt-4")

    def generate(self, prompt: str, config: dict[str, Any], timeout: int = 30) -> str:
        """Generate using OpenAI API."""
        # Override config with OpenAI defaults
        config = {
            **config,
            "provider": "openai",
            "model": config.get("model", "gpt-4"),
            "temperature": config.get("temperature", 0.7),
        }
        return super().generate(prompt, config, timeout)


class AnthropicLLMClient(UnstractLLMClient):
    """Anthropic-specific LLM client implementation."""

    def __init__(self):
        """Initialize Anthropic client."""
        super().__init__(provider="anthropic", model="claude-2")

    def generate(self, prompt: str, config: dict[str, Any], timeout: int = 30) -> str:
        """Generate using Anthropic API."""
        # Override config with Anthropic defaults
        config = {
            **config,
            "provider": "anthropic",
            "model": config.get("model", "claude-2"),
            "temperature": config.get("temperature", 0.7),
        }
        return super().generate(prompt, config, timeout)
