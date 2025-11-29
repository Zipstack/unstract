"""Adapter Helper for Vibe Extractor.

This module converts platform AdapterInstance to autogen-compatible LLM configuration.
"""

import logging
from typing import Any

from adapter_processor_v2.models import AdapterInstance

logger = logging.getLogger(__name__)


class AdapterHelper:
    """Helper to convert AdapterInstance to LLM configuration."""

    # Mapping of adapter_id to autogen adapter_id
    ADAPTER_ID_MAPPING = {
        # OpenAI adapters
        "openai": "openai",
        "openai-llm": "openai",
        # Azure OpenAI adapters
        "azure-openai": "azureopenai",
        "azureopenai": "azureopenai",
        # Anthropic adapters
        "anthropic": "anthropic",
        "claude": "anthropic",
        # Bedrock adapters
        "bedrock": "bedrock",
        "aws-bedrock": "bedrock",
    }

    @staticmethod
    def get_autogen_adapter_id(adapter_id: str) -> str:
        """Get autogen-compatible adapter ID.

        Args:
            adapter_id: Platform adapter ID

        Returns:
            Autogen adapter ID (openai, azureopenai, anthropic, bedrock)
        """
        # Normalize adapter_id
        normalized_id = adapter_id.lower().strip()

        # Check mapping
        for key, value in AdapterHelper.ADAPTER_ID_MAPPING.items():
            if key in normalized_id:
                return value

        # Default to openai if not found
        logger.warning(f"Unknown adapter_id: {adapter_id}. Defaulting to 'openai'")
        return "openai"

    @staticmethod
    def convert_to_llm_config(adapter: AdapterInstance) -> dict[str, Any]:
        """Convert AdapterInstance to autogen LLM configuration.

        Args:
            adapter: AdapterInstance from platform

        Returns:
            LLM configuration dictionary for autogen

        Raises:
            ValueError: If adapter type is not LLM
        """
        # Validate adapter type
        if adapter.adapter_type != "LLM":
            raise ValueError(f"Adapter must be of type LLM, got: {adapter.adapter_type}")

        # Get decrypted metadata
        metadata = adapter.metadata

        # Get autogen adapter ID
        autogen_adapter_id = AdapterHelper.get_autogen_adapter_id(adapter.adapter_id)

        # Base configuration
        llm_config = {
            "adapter_id": autogen_adapter_id,
            "model": metadata.get("model", metadata.get("deployment", "gpt-4")),
            "temperature": float(metadata.get("temperature", 0.7)),
            "max_tokens": int(metadata.get("max_tokens", 4096)),
        }

        # Provider-specific configuration
        if autogen_adapter_id == "openai":
            llm_config["api_key"] = metadata.get("api_key", "")
            if "api_base" in metadata:
                llm_config["api_base"] = metadata["api_base"]
            if "timeout" in metadata:
                llm_config["timeout"] = int(metadata["timeout"])
            if "max_retries" in metadata:
                llm_config["max_retries"] = int(metadata["max_retries"])

        elif autogen_adapter_id == "azureopenai":
            llm_config["api_key"] = metadata.get("api_key", "")
            llm_config["api_base"] = metadata.get(
                "azure_endpoint", metadata.get("api_base", "")
            )
            llm_config["api_version"] = metadata.get("api_version", "2024-02-15-preview")
            llm_config["deployment"] = metadata.get("deployment", metadata.get("model"))
            if "timeout" in metadata:
                llm_config["timeout"] = int(metadata["timeout"])

        elif autogen_adapter_id == "anthropic":
            llm_config["api_key"] = metadata.get("api_key", "")
            if "api_base" in metadata:
                llm_config["api_base"] = metadata["api_base"]

        elif autogen_adapter_id == "bedrock":
            llm_config["aws_access_key_id"] = metadata.get("aws_access_key_id", "")
            llm_config["aws_secret_access_key"] = metadata.get(
                "aws_secret_access_key", ""
            )
            llm_config["region_name"] = metadata.get("region_name", "us-east-1")
            if "max_retries" in metadata:
                llm_config["max_retries"] = int(metadata["max_retries"])
            if "budget_tokens" in metadata:
                llm_config["budget_tokens"] = int(metadata["budget_tokens"])
            if "timeout" in metadata:
                llm_config["timeout"] = int(metadata["timeout"])

        # Add provider for tracking
        llm_config["provider"] = adapter.adapter_id

        return llm_config

    @staticmethod
    def validate_llm_adapter(adapter: AdapterInstance) -> tuple[bool, str]:
        """Validate that adapter is suitable for vibe extraction.

        Args:
            adapter: AdapterInstance to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check adapter type
        if adapter.adapter_type != "LLM":
            return False, f"Adapter must be of type LLM, got: {adapter.adapter_type}"

        # Check if adapter is usable
        if not adapter.is_usable:
            return False, "Adapter is not usable"

        # Check if adapter is active
        if not adapter.is_active:
            return (
                False,
                "Adapter is not active. Please activate it in platform settings.",
            )

        # Try to get metadata
        try:
            metadata = adapter.metadata
            if not metadata:
                return False, "Adapter metadata is empty"
        except Exception as e:
            return False, f"Error reading adapter metadata: {str(e)}"

        # Check for required fields
        required_fields = ["model"]
        autogen_adapter_id = AdapterHelper.get_autogen_adapter_id(adapter.adapter_id)

        if autogen_adapter_id in ["openai", "azureopenai", "anthropic"]:
            required_fields.append("api_key")
        elif autogen_adapter_id == "bedrock":
            required_fields.extend(
                ["aws_access_key_id", "aws_secret_access_key", "region_name"]
            )

        missing_fields = [field for field in required_fields if not metadata.get(field)]
        if missing_fields:
            return (
                False,
                f"Missing required fields in adapter metadata: {', '.join(missing_fields)}",
            )

        return True, ""
