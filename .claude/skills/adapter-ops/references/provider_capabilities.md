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

Always verify the provider name before implementing an adapter:

```bash
# Check all unique litellm_provider values
curl -s https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json | \
  jq 'to_entries | map(select(.value.litellm_provider != null)) |
      map(.value.litellm_provider) | unique | sort'

# Check specific provider (e.g., for azure_ai models)
curl -s https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json | \
  jq 'to_entries | map(select(.key | startswith("azure_ai"))) | .[0].value.litellm_provider'
```

### Why This Matters

The cost calculation flow:
1. `LLM._record_usage()` calls `Audit.push_usage_data()` with provider from `get_provider()`
2. Platform service receives usage data with provider name
3. `CostCalculationHelper.calculate_cost()` filters models where `provider in litellm_provider`
4. If no match found, cost = $0

**Example bug**: If `get_provider()` returns `"azure_ai_foundry"` but LiteLLM uses `"azure_ai"`:
- Check: `"azure_ai_foundry" in "azure_ai"` = `False`
- Result: Cost calculation returns $0

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
