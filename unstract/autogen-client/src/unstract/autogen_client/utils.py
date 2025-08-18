"""Utility functions for Unstract AutoGen Adapter."""

import logging
from typing import Any, Dict, List, Optional, Union

from autogen_core.models import (
    AssistantMessage,
    FunctionExecutionResultMessage,
    RequestUsage,
    SystemMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

_ALLOWED_FINISH_REASONS = {
    "stop",
    "length",
    "function_calls",
    "content_filter",
    "unknown",
}


def normalize_finish_reason(raw: Optional[str]) -> str:
    """Normalize finish reason to standard values.

    Args:
        raw: Raw finish reason from adapter response

    Returns:
        Normalized finish reason (defaults to 'stop' if None)
    """
    if raw is None:
        return "stop"  # Default to 'stop' if None
    if raw == "stop_sequence":
        return "stop"
    return raw if raw in _ALLOWED_FINISH_REASONS else "unknown"


def normalize_messages(
    messages: list[
        Union[
            dict,
            SystemMessage,
            UserMessage,
            AssistantMessage,
            FunctionExecutionResultMessage,
        ]
    ],
) -> list[dict[str, str]]:
    """Normalize messages to standard format.

    Args:
        messages: List of AutoGen message objects or dicts

    Returns:
        List of message dictionaries
    """
    out: list[dict[str, str]] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
        elif isinstance(m, SystemMessage):
            out.append({"role": "system", "content": m.content})
        elif isinstance(m, UserMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AssistantMessage):
            out.append({"role": "assistant", "content": m.content})
        elif isinstance(m, FunctionExecutionResultMessage):
            out.append({"role": "function", "content": m.content})
        else:
            # Fallback for any other message type
            content = getattr(m, "content", "")
            out.append({"role": "user", "content": str(content)})
    return out


def estimate_token_count(messages: list[dict[str, str]]) -> int:
    """Estimate token count for messages using simple word-based counting.

    Args:
        messages: List of message dictionaries

    Returns:
        Estimated token count
    """
    total_content = " ".join(
        msg.get("content", "")
        for msg in messages
        if isinstance(msg.get("content"), str)
    )
    return max(1, len(total_content.split()))


def extract_content(response: Any) -> str:
    """Extract content from adapter response.

    Args:
        response: Response from Unstract LLM adapter

    Returns:
        Response content string
    """
    try:
        # First, try SDK1 format: {"response": {"text": "content"}}
        if isinstance(response, dict) and "response" in response:
            sdk1_response = response["response"]
            if isinstance(sdk1_response, dict) and "text" in sdk1_response:
                return sdk1_response["text"] or ""

        # Then try OpenAI-like format with choices
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                return choice.message.content or ""

        return ""
    except Exception as e:
        logger.warning(f"Failed to extract content: {e}")
        return ""


def extract_usage(response: Any) -> RequestUsage:
    """Extract usage information from adapter response.

    Args:
        response: Response from Unstract LLM adapter

    Returns:
        RequestUsage object
    """
    try:
        if isinstance(response, dict) and "usage" in response:
            usage = response["usage"]
            return RequestUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
    except Exception as e:
        logger.warning(f"Failed to extract usage: {e}")

    return RequestUsage(prompt_tokens=0, completion_tokens=0)


def extract_finish_reason(response: Any) -> str:
    """Extract and normalize finish reason from adapter response.

    Args:
        response: Response from Unstract LLM adapter

    Returns:
        Normalized finish reason (defaults to 'stop')
    """
    try:
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            raw_reason = getattr(choice, "finish_reason", None)
            return normalize_finish_reason(raw_reason)
    except Exception as e:
        logger.warning(f"Failed to extract finish reason: {e}")

    return normalize_finish_reason(None)  # This will return 'stop'


def validate_adapter(adapter: Any) -> bool:
    """Validate that an adapter has the required completion method.

    Args:
        adapter: Adapter instance to validate

    Returns:
        True if adapter is valid

    Raises:
        ValueError: If adapter is invalid
    """
    if not adapter:
        raise ValueError("Adapter cannot be None")

    if not hasattr(adapter, "completion"):
        raise ValueError("Adapter must have a 'completion' method")

    if not callable(adapter.completion):
        raise ValueError("Adapter 'completion' must be callable")

    return True
