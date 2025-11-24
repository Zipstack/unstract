"""LLM Bridge: Connects Unstract SDK LLM to AutoGen ChatCompletionClient.

This bridge allows AutoGen agents to use Unstract's adapter ecosystem,
enabling seamless integration without direct API key management.
"""

import logging
from typing import Any, AsyncGenerator, Sequence, Union

from autogen_core.models import (
    ChatCompletionClient,
    CreateResult,
    LLMMessage,
    RequestUsage,
)
from unstract.sdk1.llm import LLM as UnstractLLM
from unstract.prompt_service.helpers.prompt_ide_base_tool import PromptServiceBaseTool

logger = logging.getLogger(__name__)


class UnstractAutogenBridge(ChatCompletionClient):
    """Bridges Unstract SDK LLM to AutoGen's ChatCompletionClient interface.

    This allows AutoGen agents to use Unstract's adapter ecosystem
    (OpenAI, Anthropic, Bedrock, etc.) without direct API key management.

    All usage is tracked through Unstract's usage system.
    """

    def __init__(
        self,
        adapter_instance_id: str,
        platform_api_key: str,
        organization_id: str,
        workflow_id: str = None,
        execution_id: str = None,
        **kwargs,
    ):
        """Initialize bridge with Unstract adapter instance.

        Args:
            adapter_instance_id: UUID of the Unstract AdapterInstance
            platform_api_key: Unstract platform API key for SDK authentication
            organization_id: Organization ID for usage tracking
            workflow_id: Optional workflow ID for usage tracking
            execution_id: Optional execution ID for usage tracking
            **kwargs: Additional arguments passed to Unstract SDK
        """
        self.adapter_instance_id = adapter_instance_id
        self.platform_api_key = platform_api_key
        self.organization_id = organization_id
        self.workflow_id = workflow_id
        self.execution_id = execution_id

        # Create tool utility with platform key for SDK authentication
        tool = PromptServiceBaseTool(platform_key=platform_api_key)

        # Initialize Unstract LLM (uses SDK's adapter system)
        self.llm = UnstractLLM(
            tool=tool,
            adapter_instance_id=adapter_instance_id,
            usage_kwargs={
                "organization_id": organization_id,
                "workflow_id": workflow_id,
                "execution_id": execution_id,
            },
            **kwargs,
        )

        logger.info(
            f"Initialized UnstractAutogenBridge with adapter: {adapter_instance_id}"
        )

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        cancellation_token: Any = None,
        **kwargs,
    ) -> CreateResult:
        """Create a chat completion (AutoGen requirement).

        Args:
            messages: Sequence of chat messages
            cancellation_token: Optional cancellation token (not used)
            **kwargs: Additional LLM parameters (temperature, max_tokens, etc.)

        Returns:
            CreateResult with completion response
        """
        # Convert AutoGen messages to Unstract format
        prompt = self._convert_messages_to_prompt(messages)

        # Call Unstract SDK (handles usage tracking, retries, etc.)
        try:
            response = await self._call_unstract_llm(prompt, **kwargs)

            # Convert back to AutoGen format
            return self._convert_to_create_result(response)

        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            raise

    async def create_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        cancellation_token: Any = None,
        **kwargs,
    ) -> AsyncGenerator[Union[str, CreateResult], None]:
        """Create a streaming chat completion.

        Args:
            messages: Sequence of chat messages
            cancellation_token: Optional cancellation token
            **kwargs: Additional LLM parameters

        Yields:
            Chunks of completion text or final CreateResult
        """
        prompt = self._convert_messages_to_prompt(messages)

        # TODO: Use Unstract SDK's streaming if available
        # For now, fall back to non-streaming
        result = await self.create(messages, **kwargs)
        yield result.content

    def _convert_messages_to_prompt(self, messages: Sequence[LLMMessage]) -> str:
        """Convert AutoGen message format to a single prompt string.

        AutoGen messages have roles: system, user, assistant.
        We'll format them for the Unstract SDK.

        Args:
            messages: Sequence of LLMMessage objects

        Returns:
            Formatted prompt string
        """
        prompt_parts = []

        for message in messages:
            role = getattr(message, "role", "user")
            content = getattr(message, "content", "")

            if isinstance(content, str):
                if role == "system":
                    prompt_parts.append(f"System: {content}")
                elif role == "user":
                    prompt_parts.append(f"User: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"Assistant: {content}")
            elif isinstance(content, list):
                # Handle multi-modal content (text + images)
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        prompt_parts.append(f"{role.capitalize()}: {item.get('text', '')}")

        prompt = "\n\n".join(prompt_parts)
        logger.debug(f"Converted {len(messages)} messages to prompt ({len(prompt)} chars)")
        return prompt

    async def _call_unstract_llm(self, prompt: str, **kwargs) -> dict:
        """Call Unstract SDK LLM with error handling.

        Args:
            prompt: Formatted prompt string
            **kwargs: LLM parameters

        Returns:
            Dict with LLM response
        """
        # Extract common parameters
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")

        # Build Unstract SDK parameters
        llm_params = {}
        if temperature is not None:
            llm_params["temperature"] = temperature
        if max_tokens is not None:
            llm_params["max_tokens"] = max_tokens

        # Call Unstract SDK
        # Note: SDK methods might be sync, adapt as needed
        try:
            # SDK returns: {"response": LLMResponseCompat object, ...}
            sdk_response = self.llm.complete(prompt, **llm_params)

            # Extract text from response object
            response_obj = sdk_response.get("response")
            if response_obj and hasattr(response_obj, "text"):
                response_text = response_obj.text
            elif isinstance(response_obj, str):
                response_text = response_obj
            else:
                # Fallback: try to convert to string
                response_text = str(response_obj)

            # Return formatted response
            return {
                "content": response_text,
                "usage": {
                    # TODO: Get actual usage from SDK if available
                    "prompt_tokens": self._estimate_tokens(prompt),
                    "completion_tokens": self._estimate_tokens(response_text),
                },
            }

        except Exception as e:
            logger.error(f"Unstract SDK call failed: {e}")
            raise

    def _convert_to_create_result(self, unstract_response: dict) -> CreateResult:
        """Convert Unstract SDK response to AutoGen CreateResult.

        Args:
            unstract_response: Response dict from Unstract SDK

        Returns:
            CreateResult compatible with AutoGen
        """
        content = unstract_response.get("content", "")
        usage_data = unstract_response.get("usage", {})

        # Create RequestUsage
        usage = RequestUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
        )

        # Create CreateResult
        # Note: Adjust field names based on actual AutoGen CreateResult structure
        return CreateResult(
            content=content,
            usage=usage,
            finish_reason="stop",  # Assume normal completion
            cached=False,
        )

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars ≈ 1 token).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4

    @property
    def capabilities(self) -> dict:
        """Return model capabilities.

        Returns:
            Dict describing model capabilities
        """
        return {
            "vision": False,  # Update based on adapter type
            "function_calling": False,
            "json_output": True,
        }

    def count_tokens(self, messages: Sequence[LLMMessage], **kwargs) -> int:
        """Count tokens in messages.

        Args:
            messages: Messages to count
            **kwargs: Additional parameters

        Returns:
            Estimated token count
        """
        prompt = self._convert_messages_to_prompt(messages)
        return self._estimate_tokens(prompt)

    def remaining_tokens(self, messages: Sequence[LLMMessage], **kwargs) -> int:
        """Calculate remaining tokens for context window.

        Args:
            messages: Current messages
            **kwargs: Additional parameters

        Returns:
            Estimated remaining tokens (assumes 4096 context)
        """
        used = self.count_tokens(messages, **kwargs)
        # Default context size - adjust based on actual model
        context_size = 4096
        return max(0, context_size - used)

    @property
    def actual_usage(self) -> RequestUsage:
        """Return actual usage from last call.

        Returns:
            RequestUsage object
        """
        # TODO: Track actual usage from Unstract SDK
        return RequestUsage(prompt_tokens=0, completion_tokens=0)

    @property
    def total_usage(self) -> RequestUsage:
        """Return total usage across all calls.

        Returns:
            RequestUsage object
        """
        # TODO: Aggregate usage tracking
        return RequestUsage(prompt_tokens=0, completion_tokens=0)

    @property
    def model_info(self) -> dict:
        """Return information about the underlying model.

        Returns:
            Dict with model information
        """
        return {
            "adapter_instance_id": self.adapter_instance_id,
            "organization_id": self.organization_id,
            "bridge": "UnstractAutogenBridge",
        }
