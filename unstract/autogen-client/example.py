#!/usr/bin/env python3
"""
Example usage of Unstract AutoGen Client.

This example shows how to use the UnstractAutoGenClient with an Unstract LLM adapter
to create AutoGen-compatible chat completions.
"""

import asyncio
from typing import Any

from autogen_core.models import SystemMessage, UserMessage
from unstract.autogen_client import UnstractAutoGenClient


class MockUnstractAdapter:
    """Mock Unstract LLM adapter for demonstration purposes.

    In real usage, you would use your actual Unstract LLM adapter instance.
    """

    def completion(self, messages: list, **kwargs: Any) -> Any:
        """Mock completion method that returns a mock response."""

        class MockResponse:
            def __init__(self):
                self.choices = [MockChoice()]
                self.usage = MockUsage()
                self.cached = False

        class MockChoice:
            def __init__(self):
                self.message = MockMessage()
                self.finish_reason = "stop"

        class MockMessage:
            def __init__(self):
                # Simple mock response based on input
                user_msg = next((m for m in messages if m.get("role") == "user"), {})
                content = user_msg.get("content", "")

                if "hello" in content.lower():
                    self.content = "Hello! I'm an AI assistant powered by Unstract. How can I help you today?"
                elif "name" in content.lower():
                    self.content = "I'm an AI assistant created by Unstract using their LLM adapter technology."
                else:
                    self.content = (
                        f"I received your message: '{content}'. How can I assist you?"
                    )

        class MockUsage:
            def __init__(self):
                self.prompt_tokens = 10
                self.completion_tokens = 15
                self.total_tokens = 25

        return MockResponse()


async def main():
    """Main example function."""

    print("🚀 Unstract AutoGen Client Example")
    print("=" * 40)

    # Create a mock Unstract LLM adapter
    # In real usage, you would instantiate your actual Unstract adapter here:
    # adapter = UnstractLLMAdapter(provider="openai", model="gpt-4", api_key="...")
    adapter = MockUnstractAdapter()

    # Create the AutoGen client
    client = UnstractAutoGenClient(
        llm_adapter=adapter, timeout=30.0, enable_retries=True, max_retries=2
    )

    print(f"✅ Created client with capabilities: {client.capabilities()}")
    print()

    # Example 1: Simple conversation
    print("📝 Example 1: Simple Conversation")
    print("-" * 30)

    messages = [UserMessage(content="Hello there!", source="user")]

    response = await client.create(messages)
    print("User: Hello there!")
    print(f"Assistant: {response.content}")
    print(
        f"Usage: {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion = {response.usage.total_tokens} total tokens"
    )
    print()

    # Example 2: Conversation with system message
    print("📝 Example 2: With System Message")
    print("-" * 30)

    messages = [
        SystemMessage(
            content="You are a helpful assistant that answers questions about Unstract.",
            source="system",
        ),
        UserMessage(content="What's your name?", source="user"),
    ]

    response = await client.create(messages)
    print("System: You are a helpful assistant that answers questions about Unstract.")
    print("User: What's your name?")
    print(f"Assistant: {response.content}")
    print()

    # Example 3: Usage tracking
    print("📊 Example 3: Usage Tracking")
    print("-" * 30)

    print(
        f"Total usage across all requests: {client.total_usage().total_tokens} tokens"
    )
    print(f"Last request usage: {client.actual_usage().total_tokens} tokens")
    print(f"Remaining tokens: {client.remaining_tokens()}")
    print()

    # Example 4: Token counting
    print("🔢 Example 4: Token Counting")
    print("-" * 30)

    test_messages = [
        {"role": "user", "content": "Count the tokens in this message"},
        {"role": "assistant", "content": "I can estimate tokens for you"},
    ]

    token_count = client.count_tokens(test_messages)
    print(f"Estimated tokens in test messages: {token_count}")
    print()

    # Clean up
    await client.close()
    print("✅ Client closed successfully")


async def streaming_example():
    """Example of streaming completion."""
    print("\n🌊 Streaming Example")
    print("=" * 40)

    adapter = MockUnstractAdapter()
    client = UnstractAutoGenClient(llm_adapter=adapter)

    messages = [UserMessage(content="Tell me about Unstract", source="user")]

    print("User: Tell me about Unstract")
    print("Assistant: ", end="", flush=True)

    try:
        # Note: This is a simplified streaming example
        # The mock adapter doesn't actually support streaming,
        # so we'll just show the pattern
        response = await client.create(messages)
        print(response.content)
        print(f"\nStreaming completed. Tokens used: {response.usage.total_tokens}")
    except Exception as e:
        print(f"Streaming not supported by mock adapter: {e}")

    await client.close()


if __name__ == "__main__":
    # Run the main example
    asyncio.run(main())

    # Run the streaming example
    asyncio.run(streaming_example())
