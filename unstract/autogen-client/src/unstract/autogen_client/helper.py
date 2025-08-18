"""Helper functions for using AutoGen with Unstract without requiring AutoGen dependencies.

This module provides simplified interfaces to use AutoGen functionality through
the Unstract AutoGen client without requiring the consuming service to have
AutoGen dependencies installed.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .client import UnstractAutoGenClient
from .exceptions import UnstractCompletionError

logger = logging.getLogger(__name__)


class SimpleAutoGenAgent:
    """Simplified AutoGen agent that works without AutoGen dependencies.

    This class provides a simple interface to use AutoGen-like functionality
    through the Unstract AutoGen client.
    """

    def __init__(
        self,
        llm_adapter: Any,
        system_message: Optional[str] = None,
        name: str = "assistant",
        timeout: float = 30.0,
        enable_retries: bool = True,
        max_retries: int = 2,
    ):
        """Initialize simple AutoGen agent.

        Args:
            llm_adapter: Unstract LLM adapter instance
            system_message: System message to set the agent's behavior
            name: Name of the agent
            timeout: Request timeout in seconds
            enable_retries: Whether to enable automatic retries
            max_retries: Maximum number of retry attempts
        """
        self.llm_adapter = llm_adapter
        self.system_message = system_message or "You are a helpful AI assistant."
        self.name = name
        self.client = UnstractAutoGenClient(
            llm_adapter=llm_adapter,
            timeout=timeout,
            enable_retries=enable_retries,
            max_retries=max_retries,
        )
        self.conversation_history: list[dict[str, str]] = []

    async def process_message_async(
        self,
        message: str,
        context: Optional[str] = None,
        include_history: bool = True,
    ) -> dict[str, Any]:
        """Process a message asynchronously.

        Args:
            message: The user message to process
            context: Optional context to include
            include_history: Whether to include conversation history

        Returns:
            Dictionary containing response and metadata
        """
        # Build messages list
        messages = []

        # Add system message
        messages.append({"role": "system", "content": self.system_message})

        # Add context if provided
        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})

        # Add conversation history if requested
        if include_history:
            messages.extend(self.conversation_history)

        # Add current user message
        messages.append({"role": "user", "content": message})

        try:
            # Get response from client
            response = await self.client.create(messages)

            # Extract content
            content = response.content

            # Update conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": content})

            # Keep history size manageable (last 10 exchanges)
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            return {
                "response": content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.prompt_tokens
                    + response.usage.completion_tokens,
                },
                "finish_reason": response.finish_reason,
                "cached": response.cached,
            }

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise UnstractCompletionError(f"Failed to process message: {e}")

    def process_message(
        self,
        message: str,
        context: Optional[str] = None,
        include_history: bool = True,
    ) -> dict[str, Any]:
        """Process a message synchronously.

        Args:
            message: The user message to process
            context: Optional context to include
            include_history: Whether to include conversation history

        Returns:
            Dictionary containing response and metadata
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.process_message_async(message, context, include_history)
            )
        finally:
            loop.close()

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        await self.client.close()


def create_simple_autogen_agent(
    llm_adapter: Any, system_message: Optional[str] = None, **kwargs: Any
) -> SimpleAutoGenAgent:
    """Factory function to create a simple AutoGen agent.

    Args:
        llm_adapter: Unstract LLM adapter instance
        system_message: System message to set the agent's behavior
        **kwargs: Additional arguments passed to SimpleAutoGenAgent

    Returns:
        SimpleAutoGenAgent instance
    """
    return SimpleAutoGenAgent(
        llm_adapter=llm_adapter, system_message=system_message, **kwargs
    )


async def process_with_autogen_async(
    llm_adapter: Any,
    prompt: str,
    system_message: Optional[str] = None,
    context: Optional[str] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Process a single prompt using AutoGen functionality asynchronously.

    This is a convenience function for one-off processing without
    maintaining conversation state.

    Args:
        llm_adapter: Unstract LLM adapter instance
        prompt: The prompt to process
        system_message: Optional system message
        context: Optional context to include
        **kwargs: Additional arguments for the client

    Returns:
        Dictionary containing response and metadata
    """
    client = UnstractAutoGenClient(llm_adapter=llm_adapter, **kwargs)

    try:
        # Build messages
        messages = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})

        messages.append({"role": "user", "content": prompt})

        # Get response
        response = await client.create(messages)

        return {
            "response": response.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.prompt_tokens
                + response.usage.completion_tokens,
            },
            "finish_reason": response.finish_reason,
            "cached": response.cached,
            "model_info": client.model_info,
        }

    finally:
        await client.close()


def process_with_autogen(
    llm_adapter: Any,
    prompt: str,
    system_message: Optional[str] = None,
    context: Optional[str] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Process a single prompt using AutoGen functionality synchronously.

    This is a convenience function for one-off processing without
    maintaining conversation state.

    Args:
        llm_adapter: Unstract LLM adapter instance
        prompt: The prompt to process
        system_message: Optional system message
        context: Optional context to include
        **kwargs: Additional arguments for the client

    Returns:
        Dictionary containing response and metadata
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            process_with_autogen_async(
                llm_adapter=llm_adapter,
                prompt=prompt,
                system_message=system_message,
                context=context,
                **kwargs,
            )
        )
    finally:
        loop.close()


# POC test function
def run_autogen_poc(llm_adapter: Any) -> dict[str, Any]:
    """Run a simple POC to test AutoGen integration.

    Args:
        llm_adapter: Unstract LLM adapter instance

    Returns:
        Dictionary containing POC results
    """
    try:
        # Test with a simple prompt
        result = process_with_autogen(
            llm_adapter=llm_adapter,
            prompt="What is 2+2? Answer in one word.",
            system_message="You are a helpful math assistant. Be concise.",
        )

        logger.info(f"AutoGen POC successful: {result['response']}")

        return {
            "success": True,
            "test": "basic_math",
            "prompt": "What is 2+2? Answer in one word.",
            "response": result["response"],
            "usage": result["usage"],
        }

    except Exception as e:
        logger.error(f"AutoGen POC failed: {e}")
        return {"success": False, "test": "basic_math", "error": str(e)}
