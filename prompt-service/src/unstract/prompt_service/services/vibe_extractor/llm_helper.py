"""LLM Helper for Vibe Extractor.

This module provides LLM client initialization and communication using autogen.
Uses autogen-ext clients where available, and creates compatible adapters for others.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from autogen_core.models import (
    ChatCompletionClient,
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from autogen_ext.models.openai import (
    AzureOpenAIChatCompletionClient,
    OpenAIChatCompletionClient,
)

# Import SDKs (available through llama-index dependencies)
try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)


# ============================================================================
# TEMPORARY TESTING METHOD - REMOVE AFTER TESTING
# ============================================================================
def get_test_llm_config() -> Dict[str, Any]:
    """Get hardcoded LLM config for testing purposes.

    TODO: REMOVE THIS AFTER TESTING - Use proper adapter configuration instead.

    This bypasses the platform settings and adapter infrastructure for quick testing.
    To use, set environment variable ANTHROPIC_API_KEY.

    Returns:
        Dict with hardcoded Anthropic configuration
    """
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable required for testing. "
            "Set it in your .env file or environment."
        )

    return {
        "adapter_id": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "api_key": api_key,
        "temperature": 0.1,
        "max_tokens": 4096,
    }
# ============================================================================
# END TEMPORARY TESTING METHOD
# ============================================================================


class AnthropicAdapter(ChatCompletionClient):
    """Adapter to make Anthropic SDK compatible with autogen's ChatCompletionClient interface."""

    def __init__(self, api_key: str, model: str, temperature: float = 0.1,
                 max_tokens: int = 4096, **kwargs):
        if anthropic is None:
            raise ImportError("anthropic package is required")

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion using Anthropic API."""
        # Convert autogen messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if isinstance(msg, UserMessage):
                anthropic_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                # Anthropic handles system messages differently
                # We'll prepend it to the first user message
                pass

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                temperature=temperature or self._temperature,
                messages=anthropic_messages,
            )

            # Return in a format compatible with autogen
            class CompletionResult:
                def __init__(self, text):
                    self.content = text
                    self.choices = [type('obj', (object,), {'message': type('obj', (object,), {'content': text})()})]

            return CompletionResult(response.content[0].text)

        except Exception as e:
            logger.error(f"Anthropic API error: {str(e)}")
            raise


class BedrockAdapter(ChatCompletionClient):
    """Adapter to make AWS Bedrock compatible with autogen's ChatCompletionClient interface."""

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str,
                 region_name: str, model: str, temperature: float = 0.1,
                 max_tokens: int = 4096, **kwargs):
        if boto3 is None:
            raise ImportError("boto3 is required for Bedrock")
u
        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )

        # Validate credentials
        try:
            session.get_credentials().get_frozen_credentials()
        except Exception as e:
            raise RuntimeError("Invalid AWS credentials") from e

        self._client = session.client('bedrock-runtime', region_name=region_name)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion using Bedrock API."""
        import json

        # Convert autogen messages to Bedrock format
        bedrock_messages = []
        for msg in messages:
            if isinstance(msg, UserMessage):
                bedrock_messages.append({"role": "user", "content": msg.content})

        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens or self._max_tokens,
                "temperature": temperature or self._temperature,
                "messages": bedrock_messages,
            })

            response = self._client.invoke_model(
                modelId=self._model,
                body=body
            )

            response_body = json.loads(response['body'].read())
            text = response_body['content'][0]['text']

            # Return in a format compatible with autogen
            class CompletionResult:
                def __init__(self, text):
                    self.content = text
                    self.choices = [type('obj', (object,), {'message': type('obj', (object,), {'content': text})()})]

            return CompletionResult(text)

        except Exception as e:
            logger.error(f"Bedrock API error: {str(e)}")
            raise


def get_llm_client(llm_config: Dict[str, Any]) -> ChatCompletionClient:
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
        ChatCompletionClient instance

    Raises:
        Exception: If client initialization fails
    """
    try:
        adapter_id = llm_config.get("adapter_id")

        if adapter_id == "azureopenai":
            return AzureOpenAIChatCompletionClient(
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
            return OpenAIChatCompletionClient(
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
            return AnthropicAdapter(
                api_key=llm_config.get("api_key"),
                model=llm_config.get("model"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
            )

        elif adapter_id == "bedrock":
            return BedrockAdapter(
                aws_access_key_id=llm_config.get("aws_access_key_id"),
                aws_secret_access_key=llm_config.get("aws_secret_access_key"),
                region_name=llm_config.get("region_name"),
                model=llm_config.get("model"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
            )

        else:
            raise ValueError(
                f"Unknown adapter_id: {adapter_id}. "
                f"Supported: openai, azureopenai, anthropic, bedrock"
            )

    except Exception as e:
        error_msg = f"Failed to initialize LLM client: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e


async def generate_with_llm(
    llm_client: ChatCompletionClient, prompt: str, max_tokens: int = 2000
) -> str:
    """Generate a response using autogen's completion interface.

    Args:
        llm_client: ChatCompletionClient instance (from get_llm_client)
        prompt: The prompt to send to the LLM
        max_tokens: Maximum tokens to generate

    Returns:
        Generated text response

    Raises:
        Exception: If generation fails
    """
    try:
        # Create messages in autogen format
        messages = [
            SystemMessage(content="You are a helpful assistant that generates document extraction metadata and prompts."),
            UserMessage(content=prompt, source="user"),
        ]

        # Use autogen's completion API
        response = await llm_client.create(
            messages=messages,
            max_tokens=max_tokens,
        )

        # Extract text from response
        if hasattr(response, 'content'):
            return response.content.strip()
        elif hasattr(response, 'choices') and len(response.choices) > 0:
            return response.choices[0].message.content.strip()
        else:
            raise ValueError("Unexpected response format from LLM")

    except Exception as e:
        error_msg = f"Failed to generate with LLM: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e


async def guess_document_type_with_llm(
    file_content: str,
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Guess document type from file content using LLM.

    Args:
        file_content: Extracted text content from the document
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - document_type: Guessed document type (if success)
            - confidence: Confidence description (if applicable)
            - primary_indicators: List of indicators found
            - document_category: Document category
            - alternative_types: List of alternative types
            - reasoning: Reasoning for the identification
            - error: Error message (if error)
    """
    try:
        from .constants import VibeExtractorBootstrapPrompts
        import json
        import re
        from json_repair import repair_json

        # Truncate content if too long (keep first 4000 characters)
        content_sample = (
            file_content[:4000] if len(file_content) > 4000 else file_content
        )

        # Create the full prompt using the constant
        full_prompt = f"""{VibeExtractorBootstrapPrompts.DOCUMENT_TYPE_IDENTIFICATION}

## Document Content to Analyze

```
{content_sample}
```

Analyze the document content above and respond with your identification in the exact JSON format specified."""

        # Get LLM client
        llm_client = get_llm_client(llm_config)

        # Generate response with higher token limit for detailed analysis
        response_text = await generate_with_llm(
            llm_client=llm_client,
            prompt=full_prompt,
            max_tokens=1000,
        )

        # Try to extract JSON from response (in case LLM added markdown)
        json_match = re.search(
            r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL
        )
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # No JSON found in response
                logger.error(
                    f"No JSON object found in LLM response: {response_text}"
                )
                return {
                    "status": "error",
                    "error": "LLM did not return a valid JSON response. "
                    "Please try again or check the LLM configuration.",
                    "raw_response": response_text[:500],
                }

        # Try to parse JSON
        response_json = None
        try:
            response_json = json.loads(json_str)
        except json.JSONDecodeError as json_error:
            # Try to repair the JSON
            logger.warning(
                f"Initial JSON parsing failed: {json_error}. "
                f"Attempting to repair JSON..."
            )
            try:
                repaired_json_str = repair_json(json_str)
                response_json = json.loads(repaired_json_str)
                logger.info("Successfully repaired and parsed JSON response")
            except Exception as repair_error:
                # JSON repair also failed
                logger.error(
                    f"Failed to repair JSON. "
                    f"Original error: {json_error}. "
                    f"Repair error: {repair_error}. "
                    f"Attempted to parse: {json_str[:200]}"
                )
                return {
                    "status": "error",
                    "error": (
                        f"Failed to parse LLM response as JSON. "
                        f"Original error: {str(json_error)}. "
                        f"JSON repair also failed: {str(repair_error)}"
                    ),
                    "raw_response": response_text[:500],
                    "attempted_json": json_str[:200],
                }

        # Validate required fields
        required_fields = ["document_type", "confidence", "reasoning"]
        missing_fields = [
            field for field in required_fields if field not in response_json
        ]

        if missing_fields:
            logger.warning(
                f"LLM response missing required fields: {missing_fields}. "
                f"Response: {response_json}"
            )
            return {
                "status": "error",
                "error": (
                    f"LLM response missing required fields: "
                    f"{', '.join(missing_fields)}"
                ),
                "partial_response": response_json,
            }

        # Successfully parsed and validated
        return {
            "status": "success",
            "document_type": response_json.get("document_type", "unknown"),
            "confidence": response_json.get("confidence", "unknown"),
            "primary_indicators": response_json.get("primary_indicators", []),
            "document_category": response_json.get(
                "document_category", "unknown"
            ),
            "alternative_types": response_json.get("alternative_types", []),
            "reasoning": response_json.get("reasoning", ""),
        }

    except Exception as e:
        error_msg = f"Failed to guess document type with LLM: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "error",
            "error": error_msg,
        }
