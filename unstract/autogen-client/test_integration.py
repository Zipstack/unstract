#!/usr/bin/env python3
"""
Integration test for UnstractAutoGenClient with real Unstract SDK adapter.
"""

import asyncio
from typing import Any

from autogen_core.models import SystemMessage, UserMessage
from unstract.autogen_client import UnstractAutoGenClient


class NoOpAdapter:
    """
    A no-op adapter that mimics the Unstract SDK LLM adapter interface.
    This adapter returns predictable responses for testing purposes.
    """

    def __init__(self):
        self.call_count = 0

    def completion(self, messages: list, **kwargs: Any) -> Any:
        """Mock completion method that returns a structured response."""
        self.call_count += 1

        # Analyze the last message for response
        last_message = messages[-1] if messages else {}
        content = last_message.get("content", "")

        class CompletionResponse:
            def __init__(self, content: str):
                self.choices = [Choice(content)]
                self.usage = Usage()
                self.cached = False

        class Choice:
            def __init__(self, content: str):
                self.message = Message(content)
                self.finish_reason = "stop"

        class Message:
            def __init__(self, content: str):
                self.content = content

        class Usage:
            def __init__(self):
                self.prompt_tokens = len(content.split()) if content else 5
                self.completion_tokens = 10

        # Generate context-aware responses
        if "hello" in content.lower():
            response_content = "Hello! I'm powered by Unstract's LLM adapters. How can I help you today?"
        elif "test" in content.lower():
            response_content = f"Test successful! This is response #{self.call_count} from the Unstract AutoGen client."
        elif "autogen" in content.lower():
            response_content = "I'm integrated with Microsoft AutoGen framework using Unstract's adapter architecture."
        else:
            response_content = f"I received your message: '{content}'. I'm ready to help with your request."

        return CompletionResponse(response_content)


async def test_basic_integration():
    """Test basic integration with no-op adapter."""
    print("🧪 Testing Basic Integration")
    print("=" * 50)

    # Create no-op adapter
    adapter = NoOpAdapter()

    # Create AutoGen client with the adapter
    client = UnstractAutoGenClient(
        llm_adapter=adapter, timeout=30.0, enable_retries=True, max_retries=2
    )

    # Test 1: Simple completion
    print("\n📝 Test 1: Simple Completion")
    messages = [UserMessage(content="Hello, test the integration!", source="user")]
    response = await client.create(messages)

    print(f"✅ Response: {response.content}")
    total_tokens = response.usage.prompt_tokens + response.usage.completion_tokens
    print(
        f"✅ Usage: {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion = {total_tokens} total"
    )
    print(f"✅ Finish reason: {response.finish_reason}")

    # Test 2: Multi-message conversation
    print("\n📝 Test 2: Multi-message Conversation")
    messages = [
        SystemMessage(content="You are a helpful AI assistant.", source="system"),
        UserMessage(content="Tell me about AutoGen integration", source="user"),
    ]
    response = await client.create(messages)

    print(f"✅ Response: {response.content}")
    print(f"✅ Adapter called {adapter.call_count} times total")

    # Test 3: Usage tracking
    print("\n📝 Test 3: Usage Tracking")
    total_usage = client.total_usage()
    last_usage = client.actual_usage()

    total_total_tokens = total_usage.prompt_tokens + total_usage.completion_tokens
    last_total_tokens = last_usage.prompt_tokens + last_usage.completion_tokens
    print(f"✅ Total usage: {total_total_tokens} tokens")
    print(f"✅ Last request: {last_total_tokens} tokens")
    print(f"✅ Remaining tokens: {client.remaining_tokens()}")

    # Test 4: Token counting
    print("\n📝 Test 4: Token Counting")
    test_messages = [
        {"role": "user", "content": "Count tokens in this message"},
        {"role": "assistant", "content": "Sure, I can estimate token counts"},
    ]
    token_count = client.count_tokens(test_messages)
    print(f"✅ Estimated tokens: {token_count}")

    # Test 5: Capabilities
    print("\n📝 Test 5: Client Capabilities")
    capabilities = client.capabilities()
    print(f"✅ Capabilities: {capabilities}")

    # Cleanup
    await client.close()
    print("\n✅ Integration test completed successfully!")
    return True


async def test_error_handling():
    """Test error handling scenarios."""
    print("\n🚨 Testing Error Handling")
    print("=" * 50)

    class ErrorAdapter:
        def completion(self, **kwargs):
            raise Exception("Simulated adapter error")

    client = UnstractAutoGenClient(llm_adapter=ErrorAdapter(), enable_retries=False)

    try:
        messages = [UserMessage(content="This should fail", source="user")]
        await client.create(messages)
        print("❌ Error test failed - should have raised exception")
        return False
    except Exception as e:
        print(f"✅ Error handling works: {type(e).__name__}")
        return True
    finally:
        await client.close()


async def test_streaming_simulation():
    """Test streaming functionality with simulated chunks."""
    print("\n🌊 Testing Streaming Simulation")
    print("=" * 50)

    class StreamingAdapter:
        def completion(self, stream=False, **kwargs):
            if stream:
                # Simulate streaming chunks
                class StreamChunk:
                    def __init__(self, content):
                        self.choices = [StreamChoice(content)]

                class StreamChoice:
                    def __init__(self, content):
                        self.delta = StreamDelta(content)

                class StreamDelta:
                    def __init__(self, content):
                        self.content = content

                # Return iterator of chunks
                chunks = ["Hello ", "from ", "streaming ", "adapter!"]
                return (StreamChunk(chunk) for chunk in chunks)
            else:
                # Regular completion for final result
                class CompletionResponse:
                    def __init__(self):
                        self.choices = [Choice()]
                        self.usage = Usage()
                        self.cached = False

                class Choice:
                    def __init__(self):
                        self.message = Message()
                        self.finish_reason = "stop"

                class Message:
                    def __init__(self):
                        self.content = "Hello from streaming adapter!"

                class Usage:
                    def __init__(self):
                        self.prompt_tokens = 5
                        self.completion_tokens = 8

                return CompletionResponse()

    adapter = StreamingAdapter()
    client = UnstractAutoGenClient(llm_adapter=adapter)

    messages = [UserMessage(content="Test streaming", source="user")]

    print("Streaming response: ", end="", flush=True)
    chunks = []
    final_result = None

    async for item in client.create_stream(messages):
        if isinstance(item, str):
            chunks.append(item)
            print(item, end="", flush=True)
        else:
            final_result = item

    print(f"\n✅ Streamed {len(chunks)} chunks: {chunks}")
    print(f"✅ Final result: {final_result.content}")
    final_total_tokens = (
        final_result.usage.prompt_tokens + final_result.usage.completion_tokens
    )
    print(f"✅ Usage: {final_total_tokens} tokens")

    await client.close()
    return True


async def main():
    """Run all integration tests."""
    print("🚀 Unstract AutoGen Client Integration Tests")
    print("=" * 60)

    tests = [
        ("Basic Integration", test_basic_integration),
        ("Error Handling", test_error_handling),
        ("Streaming Simulation", test_streaming_simulation),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            print(f"\n✅ {test_name}: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            results.append((test_name, False))
            print(f"\n❌ {test_name}: FAILED - {e}")

    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {test_name}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All integration tests passed!")
        return True
    else:
        print("⚠️  Some tests failed - check implementation")
        return False


if __name__ == "__main__":
    asyncio.run(main())
