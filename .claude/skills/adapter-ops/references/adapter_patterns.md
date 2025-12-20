# Adapter Patterns Reference

Complete code patterns for extending unstract/sdk1 adapters.

## Architecture Overview

```
unstract/sdk1/src/unstract/sdk1/adapters/
├── base1.py              # Parameter classes & base adapter
│   ├── register_adapters()      # Auto-discovery function
│   ├── BaseAdapter              # Abstract base class
│   ├── BaseChatCompletionParameters  # LLM base params
│   ├── BaseEmbeddingParameters  # Embedding base params
│   └── {Provider}Parameters     # Provider-specific params
├── adapterkit.py         # Singleton registry (Adapterkit)
├── enums.py              # AdapterTypes enum
├── llm1/                 # LLM adapters
│   ├── __init__.py       # Calls register_adapters()
│   ├── {provider}.py     # Adapter implementations
│   └── static/           # JSON schemas
└── embedding1/           # Embedding adapters
    ├── __init__.py       # Calls register_adapters()
    ├── {provider}.py     # Adapter implementations
    └── static/           # JSON schemas
```

## Registration Flow

1. `llm1/__init__.py` imports and calls `register_adapters(adapters, "LLM")`
2. `register_adapters()` scans `llm1/*.py` files
3. For each file, inspects classes ending with `LLMAdapter`
4. Checks for `get_id()` and `get_metadata()` methods
5. Stores adapter in global dict: `adapters[adapter_id] = {module, metadata}`
6. `Adapterkit` singleton merges all adapter types on init

## Complete LLM Adapter Example

### Parameter Class (base1.py)

```python
class NewProviderLLMParameters(BaseChatCompletionParameters):
    """Provider-specific parameters.

    See https://docs.litellm.ai/docs/providers/newprovider
    """

    # Required fields (no defaults)
    api_key: str

    # Optional fields (with defaults)
    api_base: str | None = None
    custom_header: str | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        """Transform and validate adapter metadata.

        This method:
        1. Applies model prefix via validate_model()
        2. Maps field names if needed (e.g., azure_endpoint -> api_base)
        3. Handles special features (reasoning, thinking)
        4. Validates with pydantic and returns clean dict
        """
        # Always set model with proper prefix
        adapter_metadata["model"] = NewProviderLLMParameters.validate_model(
            adapter_metadata
        )

        # Map custom field names to expected names
        if "endpoint" in adapter_metadata and not adapter_metadata.get("api_base"):
            adapter_metadata["api_base"] = adapter_metadata["endpoint"]

        # Validate with pydantic and return
        return NewProviderLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        """Add provider prefix to model name (idempotent).

        IMPORTANT: Must handle already-prefixed models to avoid double-prefixing.
        """
        model = adapter_metadata.get("model", "")
        if model.startswith("newprovider/"):
            return model
        return f"newprovider/{model}"
```

### Adapter Class (llm1/newprovider.py)

```python
from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, NewProviderLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class NewProviderLLMAdapter(NewProviderLLMParameters, BaseAdapter):
    """LLM adapter for New Provider.

    Multiple inheritance order matters:
    1. Parameter class first (provides validate methods)
    2. BaseAdapter second (provides abstract methods)
    """

    @staticmethod
    def get_id() -> str:
        """Return unique adapter ID in format: provider|uuid4."""
        return "newprovider|a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        """Return adapter metadata for registration."""
        return {
            "name": "New Provider",
            "version": "1.0.0",
            "adapter": NewProviderLLMAdapter,  # Reference to this class
            "description": "New Provider LLM adapter",
            "is_active": True,  # Must be True for auto-registration
        }

    @staticmethod
    def get_name() -> str:
        """Return display name."""
        return "New Provider"

    @staticmethod
    def get_description() -> str:
        """Return description."""
        return "New Provider LLM adapter"

    @staticmethod
    def get_provider() -> str:
        """Return lowercase provider identifier (used for schema path)."""
        return "newprovider"

    @staticmethod
    def get_icon() -> str:
        """Return icon path (relative to frontend assets)."""
        return "/icons/adapter-icons/NewProvider.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        """Return adapter type enum."""
        return AdapterTypes.LLM
```

### JSON Schema (llm1/static/newprovider.json)

```json
{
  "title": "New Provider LLM",
  "type": "object",
  "required": ["adapter_name", "api_key"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name",
      "default": "",
      "description": "Unique name for this adapter instance"
    },
    "api_key": {
      "type": "string",
      "title": "API Key",
      "format": "password",
      "description": "Your New Provider API key"
    },
    "model": {
      "type": "string",
      "title": "Model",
      "default": "default-model",
      "description": "Model to use"
    },
    "max_tokens": {
      "type": "number",
      "minimum": 0,
      "multipleOf": 1,
      "title": "Maximum Output Tokens"
    },
    "timeout": {
      "type": "number",
      "minimum": 0,
      "default": 900,
      "title": "Timeout (seconds)"
    }
  }
}
```

## Reasoning Configuration Pattern (OpenAI o1/o3, Mistral Magistral)

For providers supporting reasoning effort control:

### JSON Schema Addition

```json
{
  "properties": {
    "enable_reasoning": {
      "type": "boolean",
      "title": "Enable Reasoning",
      "default": false,
      "description": "Enable reasoning capabilities for supported models"
    }
  },
  "allOf": [
    {
      "if": {
        "properties": { "enable_reasoning": { "const": true } }
      },
      "then": {
        "properties": {
          "reasoning_effort": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "default": "medium",
            "title": "Reasoning Effort",
            "description": "Controls depth of reasoning"
          }
        },
        "required": ["reasoning_effort"]
      }
    },
    {
      "if": {
        "properties": { "enable_reasoning": { "const": false } }
      },
      "then": {
        "properties": {}
      }
    }
  ]
}
```

### Parameter Class Pattern

```python
@staticmethod
def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
    adapter_metadata["model"] = MyParameters.validate_model(adapter_metadata)

    # Handle reasoning configuration
    enable_reasoning = adapter_metadata.get("enable_reasoning", False)
    reasoning_effort = adapter_metadata.get("reasoning_effort")

    # Exclude control fields before validation
    validation_metadata = {
        k: v for k, v in adapter_metadata.items()
        if k not in ("enable_reasoning", "reasoning_effort")
    }

    validated = MyParameters(**validation_metadata).model_dump()

    # Add reasoning_effort back if enabled
    if enable_reasoning and reasoning_effort:
        validated["reasoning_effort"] = reasoning_effort

    return validated
```

## Thinking Configuration Pattern (Anthropic, VertexAI, Bedrock)

For providers supporting extended thinking:

### JSON Schema Addition

```json
{
  "properties": {
    "enable_thinking": {
      "type": "boolean",
      "title": "Enable Extended Thinking",
      "default": false,
      "description": "Allow extra reasoning for complex tasks"
    }
  },
  "allOf": [
    {
      "if": {
        "properties": { "enable_thinking": { "const": true } }
      },
      "then": {
        "properties": {
          "budget_tokens": {
            "type": "number",
            "minimum": 1000,
            "default": 10000,
            "title": "Thinking Budget (tokens)"
          }
        }
      }
    }
  ]
}
```

### Parameter Class Pattern

```python
@staticmethod
def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
    adapter_metadata["model"] = MyParameters.validate_model(adapter_metadata)

    # Handle thinking configuration
    enable_thinking = adapter_metadata.get("enable_thinking", False)

    # Check if thinking was previously enabled
    has_thinking_config = (
        "thinking" in adapter_metadata
        and adapter_metadata.get("thinking") is not None
    )
    if not enable_thinking and has_thinking_config:
        enable_thinking = True

    result_metadata = adapter_metadata.copy()

    if enable_thinking:
        if has_thinking_config:
            result_metadata["thinking"] = adapter_metadata["thinking"]
        else:
            thinking_config = {"type": "enabled"}
            budget_tokens = adapter_metadata.get("budget_tokens")
            if budget_tokens is not None:
                thinking_config["budget_tokens"] = budget_tokens
            result_metadata["thinking"] = thinking_config
            result_metadata["temperature"] = 1  # Required for thinking

    # Exclude control fields from validation
    validation_metadata = {
        k: v for k, v in result_metadata.items()
        if k not in ("enable_thinking", "budget_tokens", "thinking")
    }

    validated = MyParameters(**validation_metadata).model_dump()

    # Add thinking config back if enabled
    if enable_thinking and "thinking" in result_metadata:
        validated["thinking"] = result_metadata["thinking"]

    return validated
```

## Conditional Fields Pattern

For fields that appear based on other field values:

```json
{
  "properties": {
    "deployment_type": {
      "type": "string",
      "enum": ["cloud", "on-premise"],
      "default": "cloud"
    }
  },
  "allOf": [
    {
      "if": {
        "properties": { "deployment_type": { "const": "cloud" } }
      },
      "then": {
        "properties": {
          "region": {
            "type": "string",
            "enum": ["us-east-1", "us-west-2", "eu-west-1"]
          }
        },
        "required": ["region"]
      }
    },
    {
      "if": {
        "properties": { "deployment_type": { "const": "on-premise" } }
      },
      "then": {
        "properties": {
          "server_url": {
            "type": "string",
            "format": "uri",
            "title": "Server URL"
          }
        },
        "required": ["server_url"]
      }
    }
  ]
}
```

## Optional Credentials Pattern (AWS Bedrock)

For providers with multiple authentication methods (credentials, SSO profile, IAM role):

### JSON Schema

```json
{
  "required": ["adapter_name", "region_name", "model"],
  "properties": {
    "aws_access_key_id": {
      "type": "string",
      "title": "AWS Access Key ID",
      "format": "password",
      "description": "Leave empty if using AWS Profile or IAM role."
    },
    "aws_secret_access_key": {
      "type": "string",
      "title": "AWS Secret Access Key",
      "format": "password",
      "description": "Leave empty if using AWS Profile or IAM role."
    },
    "aws_profile_name": {
      "type": "string",
      "title": "AWS Profile Name",
      "description": "AWS SSO profile name. Use instead of access keys."
    }
  }
}
```

### Parameter Class Pattern

```python
class AWSBedrockLLMParameters(BaseChatCompletionParameters):
    # All credential fields are optional
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_profile_name: str | None = None
    region_name: str  # Required
```

## JSON Mode Pattern (Ollama)

For providers supporting structured JSON output:

### JSON Schema

```json
{
  "properties": {
    "json_mode": {
      "type": "boolean",
      "title": "JSON Mode",
      "default": false,
      "description": "Enable JSON mode to constrain output to valid JSON."
    }
  }
}
```

### Parameter Class Pattern

```python
@staticmethod
def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
    # Convert json_mode to response_format
    json_mode = adapter_metadata.pop("json_mode", False)

    validated = OllamaLLMParameters(**adapter_metadata).model_dump()

    if json_mode:
        validated["response_format"] = {"type": "json_object"}

    return validated
```

## Embedding Adapter Pattern

Embedding adapters follow the same structure but with different base classes:

```python
class NewProviderEmbeddingParameters(BaseEmbeddingParameters):
    """Embedding-specific parameters."""

    api_key: str
    embed_batch_size: int | None = 10

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = NewProviderEmbeddingParameters.validate_model(
            adapter_metadata
        )
        return NewProviderEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        # Embedding models often don't need prefix
        return adapter_metadata.get("model", "")


class NewProviderEmbeddingAdapter(NewProviderEmbeddingParameters, BaseAdapter):
    # Same structure as LLM adapter but with:
    # - get_adapter_type() returns AdapterTypes.EMBEDDING
    # - Different UUID in get_id()
```

## Embedding Dimensions Pattern (OpenAI, Azure)

For embedding models supporting custom output dimensions (text-embedding-3-*):

### JSON Schema

```json
{
  "properties": {
    "dimensions": {
      "type": "number",
      "minimum": 1,
      "multipleOf": 1,
      "title": "Dimensions",
      "description": "Output embedding dimensions. Only supported by text-embedding-3-* models. Leave empty for default."
    }
  }
}
```

### Parameter Class Pattern

```python
class OpenAIEmbeddingParameters(BaseEmbeddingParameters):
    api_key: str
    dimensions: int | None = None  # Optional, model-dependent
```

## Testing Adapters

```python
from unstract.sdk1.adapters.adapterkit import Adapterkit

# Get singleton instance
kit = Adapterkit()

# List all adapters
adapters = kit.get_adapters_list()
for adapter_id, info in adapters.items():
    print(f"{adapter_id}: {info['metadata']['name']}")

# Get specific adapter class
adapter_class = kit.get_adapter_class_by_adapter_id(
    "newprovider|a1b2c3d4-e5f6-7890-abcd-ef1234567890"
)

# Validate metadata
validated = adapter_class.validate({
    "model": "my-model",
    "api_key": "sk-xxx",
})
print(validated)

# Get JSON schema
schema = adapter_class.get_json_schema()
print(schema)
```

## Common Mistakes

1. **Missing `@staticmethod` decorator** - All adapter methods must be static
2. **Wrong class name suffix** - Must end with `LLMAdapter` or `EmbeddingAdapter`
3. **Double prefix in validate_model** - Always check if prefix exists first
4. **Missing `is_active: True`** - Adapter won't be registered without it
5. **Wrong inheritance order** - Parameter class must come before BaseAdapter
6. **Incorrect provider in get_provider()** - Must match filename and schema path
