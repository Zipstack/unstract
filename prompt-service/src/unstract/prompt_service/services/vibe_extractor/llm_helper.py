"""LLM Helper for Vibe Extractor.

This module provides LLM client initialization and communication
using autogen-ext, making it easy to swap between different LLM providers.
"""

import logging
from typing import Any, Dict, Union

from autogen_core.models import ModelInfo
from autogen_ext.models.anthropic import (
    AnthropicBedrockChatCompletionClient,
    AnthropicChatCompletionClient,
    BedrockInfo,
)
from autogen_ext.models.openai import (
    AzureOpenAIChatCompletionClient,
    OpenAIChatCompletionClient,
)

try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)


def get_llm_client(
    llm_config: Dict[str, Any]
) -> Union[
    OpenAIChatCompletionClient,
    AzureOpenAIChatCompletionClient,
    AnthropicChatCompletionClient,
    AnthropicBedrockChatCompletionClient,
]:
    """Initialize and return an LLM client based on configuration.

    Args:
        llm_config: Configuration dictionary containing:
            - adapter_id: Provider identifier (openai, azureopenai, anthropic, bedrock)
            - model: Model name
            - api_key: API key for the provider
            - temperature: Temperature for generation (default: 0.1)
            - max_tokens: Maximum tokens to generate (default: 4096)
            - Other provider-specific parameters

    Returns:
        Initialized LLM client

    Raises:
        Exception: If client initialization fails
    """
    try:
        llm_client = None
        adapter_id = llm_config.get("adapter_id")

        if adapter_id == "azureopenai":
            llm_client = AzureOpenAIChatCompletionClient(
                model=llm_config.get("model"),
                azure_endpoint=llm_config.get("api_base"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
                api_version=llm_config.get("api_version"),
                api_key=llm_config.get("api_key"),
                azure_deployment=llm_config.get("deployment"),
                timeout=llm_config.get("timeout", 900),
            )
        elif adapter_id == "openai":
            llm_client = OpenAIChatCompletionClient(
                model=llm_config.get("model"),
                api_key=llm_config.get("api_key"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
                request_timeout=llm_config.get("request_timeout", 60),
                base_url=llm_config.get("api_base"),
                max_retries=llm_config.get("max_retries", 3),
                timeout=llm_config.get("timeout", 900),
            )
        elif adapter_id == "anthropic":
            llm_client = AnthropicChatCompletionClient(
                model=llm_config.get("model"),
                api_key=llm_config.get("api_key"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
                base_url=llm_config.get("api_base"),
            )
        elif adapter_id == "bedrock":
            if boto3 is None:
                raise ImportError(
                    "boto3 is required for Bedrock adapter. "
                    "Install it with: pip install boto3"
                )

            session = boto3.Session(
                aws_access_key_id=llm_config["aws_access_key_id"],
                aws_secret_access_key=llm_config["aws_secret_access_key"],
                region_name=llm_config["region_name"],
            )
            try:
                session.get_credentials().get_frozen_credentials()
            except Exception as e:
                raise RuntimeError("Invalid AWS credentials") from e

            llm_client = AnthropicBedrockChatCompletionClient(
                model=llm_config.get("model"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
                max_retries=llm_config.get("max_retries", 3),
                budget_tokens=llm_config.get("budget_tokens"),
                timeout=llm_config.get("timeout", 900),
                bedrock_info=BedrockInfo(
                    aws_region=llm_config.get("region_name"),
                    aws_access_key=llm_config.get("aws_access_key_id"),
                    aws_secret_key=llm_config.get("aws_secret_access_key"),
                ),
                model_info=ModelInfo(
                    vision=False,
                    function_calling=True,
                    json_output=False,
                    family="unknown",
                    structured_output=True,
                ),
            )
        else:
            raise ValueError(
                f"Unknown adapter_id: {adapter_id}. "
                f"Supported: openai, azureopenai, anthropic, bedrock"
            )

        if llm_client is None:
            raise RuntimeError(f"Failed to initialize LLM client for {adapter_id}")

        return llm_client

    except Exception as e:
        error_msg = f"Failed to initialize LLM client: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e


async def generate_with_llm(
    llm_client: Any, prompt: str, max_tokens: int = 2000
) -> str:
    """Generate a response from the LLM client.

    Args:
        llm_client: Initialized LLM client (from get_llm_client)
        prompt: The prompt to send to the LLM
        max_tokens: Maximum tokens to generate

    Returns:
        Generated text response

    Raises:
        Exception: If generation fails
    """
    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.messages import TextMessage
        from autogen_core.model_context import BufferedChatCompletionContext

        # Create a simple assistant agent for generation
        agent = AssistantAgent(
            name="VibeExtractorGenerator",
            model_client=llm_client,
            system_message="You are a helpful assistant that generates document extraction metadata and prompts.",
            model_context=BufferedChatCompletionContext(buffer_size=2),
        )

        # Send prompt and get response
        task = TextMessage(content=prompt, source="user")
        initial_state = await agent.save_state()
        await agent.load_state(initial_state)
        response = await agent.on_messages([task], None)

        if not response or not hasattr(response.chat_message, "content"):
            raise ValueError("Failed to get response from LLM")

        return response.chat_message.content.strip()

    except Exception as e:
        error_msg = f"Failed to generate with LLM: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e
