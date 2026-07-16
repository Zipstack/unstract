# Provider Capabilities Reference

Quick reference for LLM and embedding provider features supported via LiteLLM.

## LLM Provider Features

| Provider | Reasoning | Thinking | JSON Mode | Tools | Streaming |
|----------|:---------:|:--------:|:---------:|:-----:|:---------:|
| OpenAI | ✅ o1/o3 | ❌ | ✅ | ✅ | ✅ |
| Anthropic | ❌ | ✅ Claude 3.7+ | ✅ | ✅ | ✅ |
| Azure OpenAI | ✅ o1/o3 | ❌ | ✅ | ✅ | ✅ |
| AWS Bedrock | ❌ | ✅ Claude 3.7+ | ✅ | ✅ | ✅ |
| VertexAI | ✅ Gemini 2.5 | ✅ Gemini 2.5 | ✅ | ✅ | ✅ |
| Mistral | ✅ Magistral | ❌ | ✅ | ✅ | ✅ |
| Ollama | ❌ | ❌ | ✅ | ✅ | ✅ |
| Anyscale | ❌ | ❌ | ❌ | ❌ | ✅ |

### Feature Definitions

- **Reasoning**: `enable_reasoning` + `reasoning_effort` (low/medium/high) for chain-of-thought
- **Thinking**: `enable_thinking` + `budget_tokens` for extended internal reasoning
- **JSON Mode**: `response_format` or `json_mode` for structured output
- **Tools**: Function calling / tool use capability
- **Streaming**: Token-by-token response streaming

## Embedding Provider Features

| Provider | Dimensions | Batch Size | Model Prefix |
|----------|:----------:|:----------:|:------------:|
| OpenAI | ✅ v3 only | ✅ | ❌ |
| Azure OpenAI | ✅ v3 only | ✅ | ❌ |
| AWS Bedrock | ❌ | ✅ | `bedrock/` |
| VertexAI | ✅ | ✅ | `vertex_ai/` |
| Ollama | ❌ | ✅ | ❌ |

### Feature Definitions

- **Dimensions**: Custom output embedding dimensions (only text-embedding-3-* models)
- **Batch Size**: `embed_batch_size` for controlling request batching
- **Model Prefix**: Whether LiteLLM requires provider prefix on model name

## Provider-Specific Parameters

### OpenAI LLM
```
api_key, api_base, model, max_tokens, temperature, top_p
enable_reasoning, reasoning_effort (o1/o3 models)
```

### Anthropic LLM
```
api_key, model, max_tokens, temperature
enable_thinking, budget_tokens (Claude 3.7+)
```

### Azure OpenAI LLM
```
api_key, azure_endpoint, api_version, deployment_name, model
max_tokens, temperature, enable_reasoning, reasoning_effort
```

### AWS Bedrock LLM
```
aws_access_key_id, aws_secret_access_key, region_name
aws_profile_name (SSO), model_id (inference profile ARN)
model, max_tokens, enable_thinking, budget_tokens
```

### VertexAI LLM
```
json_credentials, project, model, max_tokens, temperature
enable_thinking, budget_tokens, reasoning_effort (Gemini 2.5)
```

### Mistral LLM
```
api_key, model, max_tokens, max_retries, timeout
enable_reasoning, reasoning_effort (Magistral models)
```

### Ollama LLM
```
base_url, model, max_tokens, temperature, context_window
request_timeout, json_mode
```

### Anyscale LLM
```
api_key, api_base, model, max_tokens, max_retries, timeout
```

## Authentication Methods

| Provider | API Key | OAuth | IAM Role | SSO Profile |
|----------|:-------:|:-----:|:--------:|:-----------:|
| OpenAI | ✅ | ❌ | ❌ | ❌ |
| Anthropic | ✅ | ❌ | ❌ | ❌ |
| Azure | ✅ | ✅ | ✅ | ❌ |
| AWS Bedrock | ✅ | ❌ | ✅ | ✅ |
| VertexAI | JSON | ❌ | ✅ | ❌ |
| Mistral | ✅ | ❌ | ❌ | ❌ |
| Ollama | ❌ | ❌ | ❌ | ❌ |

## LiteLLM Model Prefixes

| Provider | LLM Prefix | Embedding Prefix |
|----------|------------|------------------|
| OpenAI | `openai/` | (none) |
| Anthropic | `anthropic/` | N/A |
| Azure | `azure/` | `azure/` |
| AWS Bedrock | `bedrock/` | `bedrock/` |
| VertexAI | `vertex_ai/` | `vertex_ai/` |
| Mistral | `mistral/` | N/A |
| Ollama | `ollama_chat/` | `ollama/` |
| Anyscale | `anyscale/` | N/A |

## LiteLLM Provider Names (for Cost Calculation)

**CRITICAL**: The `get_provider()` method in adapters MUST return a value that matches the `litellm_provider` field in LiteLLM's pricing data. This is required for cost calculation to work correctly.

| Display Name | `get_provider()` Value | Notes |
|--------------|------------------------|-------|
| OpenAI | `openai` | Standard OpenAI API |
| Anthropic | `anthropic` | Claude models |
| Azure OpenAI | `azure` | Azure-hosted OpenAI models |
| Azure AI Foundry | `azure_ai` | NOT `azure_ai_foundry` |
| AWS Bedrock | `bedrock` | Amazon Bedrock service |
| Google VertexAI | `vertex_ai` | Google Cloud AI Platform |
| Mistral | `mistral` | Mistral AI API |
| Ollama | `ollama` | Local Ollama server |
| Anyscale | `anyscale` | Anyscale Endpoints |

### Verification Command

Always verify the provider name before implementing an adapter — against the **pinned** LiteLLM
in the sdk1 venv, not upstream `main`, since `main` may price models the pinned version doesn't:

```bash
cd unstract/sdk1 && uv run python -c "
import litellm
# All unique litellm_provider values in the pinned cost map
print(sorted({v['litellm_provider'] for v in litellm.model_cost.values()
              if isinstance(v, dict) and v.get('litellm_provider')}))
# Provider for a specific model-key prefix (e.g. azure_ai)
print([v['litellm_provider'] for k, v in litellm.model_cost.items()
       if k.startswith('azure_ai')][:1])
"
```

### Why This Matters

The cost calculation flow:
1. `LLM._record_usage()` logs tokens — no cost math.
2. `Audit.push_usage_data()` (LLM) / `UsageHandler` (embedding) calls
   `litellm.cost_per_token(model=model_name)`, where `model_name` is the **prefixed** model
   string emitted by `validate_model()`.
3. No cost-map entry for that string → the call raises → the bare `except` records $0.

The `provider` value from `get_provider()` rides along into the usage row's `provider` column
but is **not** used for pricing.

**Example bug**: a branded OpenAI-compatible adapter emits `custom_openai/MiniMax-M3`. LiteLLM
prices `minimax/MiniMax-M3` but has no `custom_openai/` keys, so cost silently resolves to $0 —
even though `get_provider()` correctly returns `"minimax"`.

See `references/adapter_patterns.md` → *Model Prefix Verification* for how to choose a base
class so the prefix resolves.

## Models Supporting Advanced Features

### Reasoning Models (reasoning_effort)
- OpenAI: `o1-mini`, `o1-preview`, `o3-mini`, `o3`, `o4-mini`
- Azure: `o1-mini`, `o1-preview` (via deployment)
- Mistral: `magistral-medium-2506`, `magistral-small-2506`
- VertexAI: `gemini-2.5-flash-preview`, `gemini-2.5-pro`

### Thinking Models (budget_tokens)
- Anthropic: `claude-3-7-sonnet`, `claude-sonnet-4`, `claude-opus-4`
- Bedrock: `anthropic.claude-3-7-sonnet-*`
- VertexAI: `gemini-2.5-flash-preview`, `gemini-2.5-pro`

### Embedding Models with Dimensions
- OpenAI: `text-embedding-3-small`, `text-embedding-3-large`
- Azure: `text-embedding-3-small`, `text-embedding-3-large` (via deployment)

## Documentation Links

| Provider | LiteLLM Docs |
|----------|--------------|
| OpenAI | https://docs.litellm.ai/docs/providers/openai |
| Anthropic | https://docs.litellm.ai/docs/providers/anthropic |
| Azure | https://docs.litellm.ai/docs/providers/azure |
| Bedrock | https://docs.litellm.ai/docs/providers/bedrock |
| VertexAI | https://docs.litellm.ai/docs/providers/vertex |
| Mistral | https://docs.litellm.ai/docs/providers/mistral |
| Ollama | https://docs.litellm.ai/docs/providers/ollama |
| Embedding | https://docs.litellm.ai/docs/embedding/supported_embedding |
