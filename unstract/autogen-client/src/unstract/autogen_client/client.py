"""Unstract AutoGen Client implementation."""

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any, Optional, Union

from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    CreateResult,
    FunctionExecutionResultMessage,
    ModelInfo,
    RequestUsage,
    SystemMessage,
    UserMessage,
)

from .exceptions import (
    UnstractAutoGenError,
    UnstractCompletionError,
    UnstractConfigurationError,
    UnstractConnectionError,
    UnstractTimeoutError,
    UnstractValidationError,
)
from .utils import (
    estimate_token_count,
    extract_content,
    extract_finish_reason,
    extract_usage,
    normalize_messages,
)

logger = logging.getLogger(__name__)


class UnstractAutoGenClient(ChatCompletionClient):
    """ChatCompletionClient implementation using Unstract LLM adapters.

    This client provides a bridge between AutoGen's ChatCompletionClient interface
    and Unstract's LLM adapter completion capabilities. It uses only the Unstract
    adapter's completion method, without any external LLM library dependencies.

    Attributes:
        llm_adapter: The Unstract LLM adapter instance with completion method
        model_info: ModelInfo object containing model capabilities

    Examples:
        >>> from unstract.llm.adapter import UnstractLLMAdapter
        >>> adapter = UnstractLLMAdapter(provider="openai", model="gpt-4")
        >>> client = UnstractAutoGenClient(llm_adapter=adapter)
        >>>
        >>> response = await client.create([
        ...     UserMessage(content="Hello!", source="user")
        ... ])
        >>> print(response.content)
    """

    def __init__(
        self,
        llm_adapter: Any,
        model_info: Optional[ModelInfo] = None,
        timeout: Optional[float] = None,
        enable_retries: bool = True,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> None:
        """Initialize the Unstract AutoGen client.

        Args:
            llm_adapter: Unstract LLM adapter instance with a completion method
            model_info: Optional ModelInfo override for capabilities
            timeout: Request timeout in seconds
            enable_retries: Whether to enable automatic retries
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments (for future extensibility)

        Raises:
            UnstractConfigurationError: If configuration is invalid
        """
        # Validate that adapter has completion method
        if not llm_adapter:
            raise UnstractConfigurationError("llm_adapter must be provided")

        if not hasattr(llm_adapter, "completion"):
            raise UnstractConfigurationError(
                "llm_adapter must have a 'completion' method"
            )

        self.llm_adapter = llm_adapter
        self._timeout = timeout
        self._enable_retries = enable_retries
        self._max_retries = max_retries
        self._kwargs = kwargs

        # Set model info with sensible defaults
        self._model_info = model_info or self._get_default_model_info()

        # Track usage across requests
        self._last_usage = RequestUsage(prompt_tokens=0, completion_tokens=0)
        self._total_usage = RequestUsage(prompt_tokens=0, completion_tokens=0)

        # Closed state tracking
        self._closed = False

        logger.info("Initialized UnstractAutoGenClient with adapter")

    @property
    def model_info(self) -> ModelInfo:
        """Get model information and capabilities."""
        return self._model_info

    def capabilities(self) -> dict[str, bool]:
        """Get client capabilities.

        Returns:
            Dictionary of supported capabilities
        """
        return {
            "chat": True,
            "stream": True,
            "count_tokens": True,
            "function_calling": self._model_info.get("function_calling", False),
            "vision": self._model_info.get("vision", False),
            "json_output": self._model_info.get("json_output", False),
        }

    async def create(
        self,
        messages: list[
            Union[
                dict,
                SystemMessage,
                UserMessage,
                AssistantMessage,
                FunctionExecutionResultMessage,
            ]
        ],
        **kwargs: Any,
    ) -> CreateResult:
        """Create a chat completion.

        Args:
            messages: List of messages for the conversation
            **kwargs: Additional parameters for the completion

        Returns:
            CreateResult with the model's response

        Raises:
            UnstractCompletionError: If completion fails
        """
        if self._closed:
            raise UnstractCompletionError("Client has been closed")

        try:
            # Normalize messages to standard format
            normalized_messages = normalize_messages(messages)

            # Prepare completion parameters
            completion_params = {
                "messages": normalized_messages,
                **self._kwargs,
                **kwargs,
            }

            if self._timeout:
                completion_params["timeout"] = self._timeout

            # Execute completion using the Unstract LLM adapter
            if self._enable_retries:
                response = await self._execute_with_retry(
                    lambda: self._execute_completion(completion_params)
                )
            else:
                response = await self._execute_completion(completion_params)

            # Extract content and usage information
            content = extract_content(response)
            usage = extract_usage(response)
            finish_reason = extract_finish_reason(response)

            # Update usage tracking
            self._last_usage = usage
            self._total_usage = RequestUsage(
                prompt_tokens=self._total_usage.prompt_tokens + usage.prompt_tokens,
                completion_tokens=self._total_usage.completion_tokens
                + usage.completion_tokens,
            )

            return CreateResult(
                content=content,
                usage=usage,
                finish_reason=finish_reason,
                cached=getattr(response, "cached", False),
                logprobs=None,
                thought=None,
            )

        except Exception as e:
            raise self._handle_exception(e) from e

    async def create_stream(
        self,
        messages: list[
            Union[
                dict,
                SystemMessage,
                UserMessage,
                AssistantMessage,
                FunctionExecutionResultMessage,
            ]
        ],
        **kwargs: Any,
    ) -> AsyncIterable[Union[str, CreateResult]]:
        """Create a streaming chat completion.

        Args:
            messages: List of messages for the conversation
            **kwargs: Additional parameters for the completion

        Yields:
            String chunks during streaming, final CreateResult at the end

        Raises:
            UnstractCompletionError: If streaming fails
        """
        if self._closed:
            raise UnstractCompletionError("Client has been closed")

        try:
            # Normalize messages to standard format
            normalized_messages = normalize_messages(messages)

            # Prepare completion parameters for streaming
            completion_params = {
                "messages": normalized_messages,
                "stream": True,
                **self._kwargs,
                **kwargs,
            }

            if self._timeout:
                completion_params["timeout"] = self._timeout

            # Execute streaming completion using the adapter
            if self._enable_retries:
                stream_response = await self._execute_with_retry(
                    lambda: self._execute_streaming_completion(completion_params)
                )
            else:
                stream_response = await self._execute_streaming_completion(
                    completion_params
                )

            # Collect chunks for final result
            collected_content = []

            # Stream the response
            async for chunk in stream_response:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        collected_content.append(delta.content)
                        yield delta.content

            # Create final result by calling create with the same parameters
            # but without streaming to get complete usage info
            final_params = completion_params.copy()
            final_params["stream"] = False
            final_response = await self._execute_completion(final_params)

            # Extract final information
            final_content = "".join(collected_content)
            usage = extract_usage(final_response)
            finish_reason = extract_finish_reason(final_response)

            # Update usage tracking
            self._last_usage = usage
            self._total_usage = RequestUsage(
                prompt_tokens=self._total_usage.prompt_tokens + usage.prompt_tokens,
                completion_tokens=self._total_usage.completion_tokens
                + usage.completion_tokens,
            )

            yield CreateResult(
                content=final_content,
                usage=usage,
                finish_reason=finish_reason,
                cached=getattr(final_response, "cached", False),
                logprobs=None,
                thought=None,
            )

        except Exception as e:
            raise self._handle_exception(e) from e

    def count_tokens(self, messages: list[dict[str, str]]) -> int:
        """Count tokens in messages.

        Args:
            messages: List of messages in dict format

        Returns:
            Estimated token count
        """
        try:
            return estimate_token_count(messages)
        except Exception as e:
            logger.warning(f"Token counting failed: {e}, using fallback")
            # Fallback to simple word-based estimation
            return sum(len(m.get("content", "").split()) for m in messages)

    def remaining_tokens(self) -> int:
        """Get remaining tokens based on model's context window.

        Returns:
            Remaining tokens or -1 if unlimited/unknown
        """
        max_tokens = self._model_info.get("max_tokens")
        if max_tokens is None:
            return -1

        used_tokens = (
            self._last_usage.prompt_tokens + self._last_usage.completion_tokens
        )
        return max(0, max_tokens - used_tokens)

    def total_usage(self) -> RequestUsage:
        """Get total usage across all requests.

        Returns:
            Total RequestUsage
        """
        return self._total_usage

    def actual_usage(self) -> RequestUsage:
        """Get usage from the last request.

        Returns:
            Last RequestUsage
        """
        return self._last_usage

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        if not self._closed:
            self._closed = True
            logger.info("UnstractAutoGenClient closed")

    async def _execute_completion(self, params: dict[str, Any]) -> Any:
        """Execute a completion request using the Unstract LLM adapter.

        Args:
            params: Completion parameters

        Returns:
            Response from the Unstract LLM adapter
        """

        def _call():
            # Use the Unstract LLM adapter's completion method
            return self.llm_adapter.completion(**params)

        return await asyncio.get_event_loop().run_in_executor(None, _call)

    async def _execute_streaming_completion(self, params: dict[str, Any]) -> Any:
        """Execute a streaming completion request using the adapter.

        Args:
            params: Completion parameters

        Returns:
            Async iterator for streaming response
        """

        def _stream_call():
            # Use the Unstract LLM adapter's completion method with streaming
            return self.llm_adapter.completion(**params)

        # Execute streaming completion
        stream_response = await asyncio.get_event_loop().run_in_executor(
            None, _stream_call
        )

        # Convert to async iterator
        async def _async_stream():
            for chunk in stream_response:
                yield chunk

        return _async_stream()

    async def _execute_with_retry(self, func) -> Any:
        """Execute function with retry logic.

        Args:
            func: Function to execute

        Returns:
            Function result
        """
        last_exception = None

        for attempt in range(self._max_retries + 1):
            try:
                return await func()
            except Exception as e:
                last_exception = e
                if attempt < self._max_retries:
                    wait_time = 2**attempt  # Exponential backoff
                    logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {self._max_retries + 1} attempts failed")
                    break

        raise last_exception

    def _handle_exception(self, error: Exception) -> UnstractAutoGenError:
        """Handle and convert exceptions to Unstract-specific errors.

        Args:
            error: Original exception

        Returns:
            UnstractAutoGenError subclass
        """
        error_message = str(error).lower()

        # Timeout errors
        if "timeout" in error_message or "timed out" in error_message:
            return UnstractTimeoutError("Request timed out", original_error=error)

        # Connection errors
        if any(
            term in error_message
            for term in ["connection", "network", "dns", "unreachable"]
        ):
            return UnstractConnectionError(
                "Failed to connect to Unstract adapter", original_error=error
            )

        # Validation errors
        if any(
            term in error_message for term in ["validation", "invalid", "malformed"]
        ):
            return UnstractValidationError(
                f"Request validation failed: {error}", original_error=error
            )

        # Generic completion error
        return UnstractCompletionError(
            f"Unstract adapter completion failed: {error}", original_error=error
        )

    def _get_default_model_info(self) -> ModelInfo:
        """Get default model capabilities.

        Returns:
            ModelInfo with default capabilities
        """
        return ModelInfo(
            {
                "family": "unstract",
                "vision": True,  # Assume modern capabilities
                "function_calling": True,
                "json_output": True,
                "structured_output": True,
            }
        )
