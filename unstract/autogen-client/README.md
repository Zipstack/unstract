# Unstract AutoGen Client

A Python package that provides a ChatCompletionClient implementation for Microsoft AutoGen framework, using Unstract LLM adapters as the backend for LLM interactions.

## Features

- **Pure Unstract Integration**: Uses only Unstract LLM adapters, no external LLM library dependencies
- **AutoGen Compatible**: Implements the standard ChatCompletionClient interface
- **Async Support**: Full async/await support with proper error handling
- **Streaming**: Support for streaming completions
- **Usage Tracking**: Automatic token usage tracking and reporting
- **Error Handling**: Comprehensive error handling with specific exception types
- **Retry Logic**: Built-in retry mechanism with exponential backoff
- **Type Safety**: Full type hints for better development experience

## Installation

```bash
pip install unstract-autogen-client
```

## Quick Start

```python
from unstract.llm.adapter import UnstractLLMAdapter
from unstract.autogen_client import UnstractAutoGenClient
from autogen_core.models import UserMessage

# Create an Unstract LLM adapter
adapter = UnstractLLMAdapter(
    provider="openai",
    model="gpt-4",
    api_key="your-api-key"
)

# Create the AutoGen client
client = UnstractAutoGenClient(llm_adapter=adapter)

# Use with AutoGen
async def main():
    messages = [
        UserMessage(content="Hello! How can you help me?", source="user")
    ]
    
    response = await client.create(messages)
    print(f"Response: {response.content}")
    print(f"Tokens used: {response.usage.total_tokens}")

# Run the example
import asyncio
asyncio.run(main())
```

## Streaming Example

```python
async def streaming_example():
    messages = [
        UserMessage(content="Tell me a story", source="user")
    ]
    
    print("Streaming response:")
    async for chunk in client.create_stream(messages):
        if isinstance(chunk, str):
            print(chunk, end="", flush=True)
        else:
            # Final result with usage info
            print(f"\nTokens used: {chunk.usage.total_tokens}")

asyncio.run(streaming_example())
```

## Advanced Configuration

```python
from unstract.autogen_client import UnstractAutoGenClient
from autogen_core.models import ModelInfo

# Custom model info
model_info = ModelInfo(
    family="custom",
    vision=True,
    function_calling=True,
    json_output=True,
    max_tokens=8192,
    supports_streaming=True,
)

# Client with advanced options
client = UnstractAutoGenClient(
    llm_adapter=adapter,
    model_info=model_info,
    timeout=60.0,
    enable_retries=True,
    max_retries=3,
)

# Check client capabilities
capabilities = client.capabilities()
print(f"Supports vision: {capabilities['vision']}")
print(f"Supports function calling: {capabilities['function_calling']}")

# Usage tracking
print(f"Total tokens used: {client.total_usage().total_tokens}")
print(f"Remaining tokens: {client.remaining_tokens()}")
```

## Integration with AutoGen Agents

```python
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console

# Create AutoGen agents using the Unstract client
async def create_agent_example():
    assistant = AssistantAgent(
        name="assistant", 
        model_client=client,
        system_message="You are a helpful assistant that writes Python code."
    )
    
    # Use the Console interface for interaction
    console = Console()
    
    # Start a conversation
    result = await console.run(
        task="Help me write a Python function to calculate fibonacci numbers.",
        agent=assistant
    )
    
    return result

# Run the example
import asyncio
asyncio.run(create_agent_example())
```

## Error Handling

```python
from unstract.autogen_client import (
    UnstractCompletionError,
    UnstractTimeoutError,
    UnstractConnectionError
)

try:
    response = await client.create(messages)
except UnstractTimeoutError:
    print("Request timed out")
except UnstractConnectionError:
    print("Failed to connect to adapter")
except UnstractCompletionError as e:
    print(f"Completion failed: {e}")
```

## Requirements

- Python 3.8+
- autogen-core >= 0.4.0
- An Unstract LLM adapter instance with a `completion` method

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests to our repository.

## Support

For issues and questions:
- GitHub Issues: https://github.com/Zipstack/unstract/issues
- Documentation: https://docs.unstract.com
- Email: support@unstract.com
