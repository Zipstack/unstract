"""Configuration for X2Text adapter integration tests.

This module defines the test configurations for all X2Text (document extraction) providers.
Each provider configuration specifies the required environment variables
and adapter metadata structure.

X2Text adapters are used for document text extraction from various sources like PDFs,
images, and other document formats. Unlike LLMs/Embeddings which use LiteLLM,
X2Text adapters use various extraction libraries and APIs.
"""

import os
from typing import Any


class X2TextProviderConfig:
    """Configuration for a single X2Text provider."""

    def __init__(
        self,
        provider_name: str,
        adapter_id: str,
        required_env_vars: list[str],
        metadata_builder: callable,
        skip_reason: str | None = None,
    ):
        """Initialize provider configuration.

        Args:
            provider_name: Display name of the provider
            adapter_id: Adapter ID string
            required_env_vars: List of required environment variable names
            metadata_builder: Function that builds adapter settings from env vars
            skip_reason: Optional custom skip reason
        """
        self.provider_name = provider_name
        self.adapter_id = adapter_id
        self.required_env_vars = required_env_vars
        self.metadata_builder = metadata_builder
        self.skip_reason = skip_reason

    def is_available(self) -> bool:
        """Check if all required environment variables are set.

        Returns:
            True if provider is available for testing, False otherwise
        """
        if self.skip_reason:
            return False
        return all(os.getenv(var) for var in self.required_env_vars)

    def build_metadata(self, **overrides: Any) -> dict[str, Any]:
        """Build adapter metadata from environment variables.

        Args:
            **overrides: Optional metadata overrides

        Returns:
            Dictionary of adapter configuration metadata
        """
        metadata = self.metadata_builder()
        metadata.update(overrides)
        return metadata


# ============================================================================
# Metadata Builders
# ============================================================================


def build_llama_parse_metadata() -> dict[str, Any]:
    """Build metadata for LlamaParse adapter.

    Note: Only includes user-facing fields from JSON schema.
    adapter_name is optional in schema, api_key is required.
    """
    return {
        "adapter_name": "llama-parse-test",
        "api_key": os.getenv("LLAMA_PARSE_API_KEY", ""),
        "url": os.getenv("LLAMA_PARSE_URL", "https://api.cloud.llamaindex.ai"),
        "result_type": os.getenv("LLAMA_PARSE_RESULT_TYPE", "text"),
        "verbose": os.getenv("LLAMA_PARSE_VERBOSE", "true").lower() == "true",
    }


def build_llm_whisperer_v2_metadata() -> dict[str, Any]:
    """Build metadata for LLMWhisperer V2 adapter."""
    return {
        "adapter_name": "llm-whisperer-v2-test",
        "url": os.getenv(
            "LLM_WHISPERER_URL", "https://llmwhisperer-api.us-central.unstract.com"
        ),
        "unstract_key": os.getenv("LLM_WHISPERER_UNSTRACT_KEY", ""),
        "mode": os.getenv("LLM_WHISPERER_MODE", "form"),
        "output_mode": os.getenv("LLM_WHISPERER_OUTPUT_MODE", "layout_preserving"),
        "line_splitter_tolerance": float(
            os.getenv("LLM_WHISPERER_LINE_SPLITTER_TOLERANCE", "0.4")
        ),
        "horizontal_stretch_factor": float(
            os.getenv("LLM_WHISPERER_HORIZONTAL_STRETCH_FACTOR", "1.0")
        ),
        "page_seperator": os.getenv("LLM_WHISPERER_PAGE_SEPARATOR", "<<<"),
        "mark_vertical_lines": (
            os.getenv("LLM_WHISPERER_MARK_VERTICAL_LINES", "false").lower() == "true"
        ),
        "mark_horizontal_lines": (
            os.getenv("LLM_WHISPERER_MARK_HORIZONTAL_LINES", "false").lower() == "true"
        ),
    }


def build_no_op_metadata() -> dict[str, Any]:
    """Build metadata for NoOp adapter (testing/development only)."""
    return {
        "adapter_name": "no-op-test",
        "wait_time": float(os.getenv("NO_OP_WAIT_TIME", "0")),
    }


def build_unstructured_community_metadata() -> dict[str, Any]:
    """Build metadata for Unstructured.io Community adapter.

    Note: Only includes user-facing fields from JSON schema.
    Requires adapter_name and url (pointing to Unstructured.io server).
    """
    return {
        "adapter_name": "unstructured-community-test",
        "url": os.getenv(
            "UNSTRUCTURED_URL", "http://unstract-unstructured-io:8000/general/v0/general"
        ),
    }


# ============================================================================
# Provider Configurations
# ============================================================================

PROVIDER_CONFIGS: dict[str, X2TextProviderConfig] = {
    "llama_parse": X2TextProviderConfig(
        provider_name="LlamaParse",
        adapter_id="llamaparse|78860239-b3cc-4cc5-b3de-f84315f75d14",
        required_env_vars=["LLAMA_PARSE_API_KEY"],
        metadata_builder=build_llama_parse_metadata,
    ),
    "llm_whisperer_v2": X2TextProviderConfig(
        provider_name="LLMWhisperer V2",
        adapter_id="llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93",
        required_env_vars=["LLM_WHISPERER_UNSTRACT_KEY"],
        metadata_builder=build_llm_whisperer_v2_metadata,
    ),
    "no_op": X2TextProviderConfig(
        provider_name="NoOp X2Text",
        adapter_id="noOpX2text|mp66d1op-7100-d340-9101-846fc7115676",
        required_env_vars=[],  # No external dependencies
        metadata_builder=build_no_op_metadata,
    ),
    "unstructured_community": X2TextProviderConfig(
        provider_name="Unstructured IO Community",
        adapter_id="unstructuredcommunity|eeed506f-1875-457f-9101-846fc7115676",
        required_env_vars=["UNSTRUCTURED_URL"],  # Requires Unstructured.io server URL
        metadata_builder=build_unstructured_community_metadata,
    ),
}


def get_available_providers() -> list[str]:
    """Get list of available X2Text providers based on environment configuration.

    Returns:
        List of provider keys that have required environment variables set.
        If no providers are configured, returns a dummy list to prevent test collection errors.
    """
    available = [key for key, config in PROVIDER_CONFIGS.items() if config.is_available()]

    # Return dummy provider if no real providers are configured
    # This prevents pytest collection errors
    if not available:
        return ["__no_providers_configured__"]

    return available


# Export list for pytest parameterization
AVAILABLE_PROVIDERS = get_available_providers()
