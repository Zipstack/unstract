---
name: adapter-ops
description: Extend LLM and embedding adapters in unstract/sdk1. Use when adding new adapters (LLM or embedding), removing adapters, adding/removing models to existing adapters, or editing adapter configurations. Supports OpenAI-compatible providers, cloud providers (AWS Bedrock, VertexAI, Azure), and self-hosted models (Ollama).
---

# Unstract Adapter Extension Skill

This skill provides workflows and automation for extending LLM and embedding adapters in the `unstract/sdk1` module.

## Supported Operations

| Operation | Command | Description |
|-----------|---------|-------------|
| Add LLM Adapter | `scripts/init_llm_adapter.py` | Create new LLM provider adapter |
| Add Embedding Adapter | `scripts/init_embedding_adapter.py` | Create new embedding provider adapter |
| Remove Adapter | Manual deletion | Remove adapter files and parameter class |
| Add/Remove Models | `scripts/manage_models.py` | Modify available models in JSON schema |
| Edit Adapter | Manual edit | Modify existing adapter behavior |
| Check for Updates | `scripts/check_adapter_updates.py` | Compare adapters against LiteLLM features |

## Quick Reference

### File Locations
```
unstract/sdk1/src/unstract/sdk1/adapters/
├── base1.py              # Parameter classes (add new ones here)
├── llm1/                 # LLM adapters
│   ├── {provider}.py     # Adapter implementation
│   └── static/{provider}.json  # UI schema
└── embedding1/           # Embedding adapters
    ├── {provider}.py     # Adapter implementation
    └── static/{provider}.json  # UI schema
```

### ID Format
Adapter IDs follow the pattern: `{provider}|{uuid4}`
- Example: `openai|502ecf49-e47c-445c-9907-6d4b90c5cd17`
- Generate UUID: `python -c "import uuid; print(uuid.uuid4())"`

### Model Prefix Convention
LiteLLM requires provider prefixes on model names:
| Provider | Prefix | Example |
|----------|--------|---------|
| OpenAI | `openai/` | `openai/gpt-4` |
| Azure | `azure/` | `azure/gpt-4-deployment` |
| Anthropic | `anthropic/` | `anthropic/claude-3-opus` |
| Bedrock | `bedrock/` | `bedrock/anthropic.claude-v2` |
| VertexAI | `vertex_ai/` | `vertex_ai/gemini-pro` |
| Ollama | `ollama_chat/` | `ollama_chat/llama2` |
| Mistral | `mistral/` | `mistral/mistral-large` |
| Anyscale | `anyscale/` | `anyscale/meta-llama/Llama-2-70b` |

## Workflows

### Adding a New LLM Adapter

1. **Run initialization script**:
   ```bash
   python .claude/skills/adapter-ops/scripts/init_llm_adapter.py \
     --provider newprovider \
     --name "New Provider" \
     --description "New Provider LLM adapter" \
     --auto-logo
   ```

   **Logo options**:
   - `--auto-logo`: Search for potential logo sources (Clearbit, GitHub) and display suggestions. Does NOT auto-download - you must verify and use `--logo-url` to download.
   - `--logo-url URL`: Download logo from a verified URL (supports SVG and raster images)
   - `--logo-file PATH`: Copy logo from local file (supports SVG and raster images)

   **Logo image settings** (optimized for sharp rendering):
   - SVG conversion: 4800 DPI density, 8-bit depth, 512x512 pixels
   - Raster images: Resized to 512x512 with LANCZOS resampling
   - Requires ImageMagick for SVG conversion (`sudo pacman -S imagemagick`)

   **GitHub logo URL tip**: When downloading logos from GitHub, always use the raw URL:
   - ❌ `https://github.com/user/repo/blob/main/logo.svg`
   - ✅ `https://raw.githubusercontent.com/user/repo/main/logo.svg`

   Logos are saved to: `frontend/public/icons/adapter-icons/{ProviderName}.png`

2. **Add parameter class to `base1.py`** (if provider has unique parameters):
   ```python
   class NewProviderLLMParameters(BaseChatCompletionParameters):
       """See https://docs.litellm.ai/docs/providers/newprovider."""

       api_key: str
       # Add provider-specific fields

       @staticmethod
       def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
           adapter_metadata["model"] = NewProviderLLMParameters.validate_model(adapter_metadata)
           return NewProviderLLMParameters(**adapter_metadata).model_dump()

       @staticmethod
       def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
           model = adapter_metadata.get("model", "")
           if model.startswith("newprovider/"):
               return model
           return f"newprovider/{model}"
   ```

3. **Update adapter class** to inherit from new parameter class:
   ```python
   from unstract.sdk1.adapters.base1 import BaseAdapter, NewProviderLLMParameters

   class NewProviderLLMAdapter(NewProviderLLMParameters, BaseAdapter):
       # ... implementation
   ```

4. **Customize JSON schema** in `llm1/static/newprovider.json` for UI configuration

5. **Test the adapter**:
   ```python
   from unstract.sdk1.adapters.adapterkit import Adapterkit
   kit = Adapterkit()
   adapters = kit.get_adapters_list()
   # Verify new adapter appears
   ```

### Adding a New Embedding Adapter

1. **Run initialization script**:
   ```bash
   python .claude/skills/adapter-ops/scripts/init_embedding_adapter.py \
     --provider newprovider \
     --name "New Provider" \
     --description "New Provider embedding adapter" \
     --auto-logo
   ```

   Same logo options as LLM adapter: `--auto-logo` (search only), `--logo-url`, `--logo-file`

2. **Add parameter class to `base1.py`** (if needed):
   ```python
   class NewProviderEmbeddingParameters(BaseEmbeddingParameters):
       """See https://docs.litellm.ai/docs/providers/newprovider."""

       api_key: str
       embed_batch_size: int | None = 10

       @staticmethod
       def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
           adapter_metadata["model"] = NewProviderEmbeddingParameters.validate_model(adapter_metadata)
           return NewProviderEmbeddingParameters(**adapter_metadata).model_dump()

       @staticmethod
       def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
           return adapter_metadata.get("model", "")
   ```

3. **Update adapter class and JSON schema**

### Removing an Adapter

1. **Delete adapter file**: `llm1/{provider}.py` or `embedding1/{provider}.py`
2. **Delete JSON schema**: `llm1/static/{provider}.json` or `embedding1/static/{provider}.json`
3. **Remove parameter class** from `base1.py` (if dedicated class exists)
4. **Verify removal**: Run `Adapterkit().get_adapters_list()` to confirm

### Adding/Removing Models from Existing Adapter

1. **Edit JSON schema** (`static/{provider}.json`):
   ```json
   {
     "properties": {
       "model": {
         "type": "string",
         "title": "Model",
         "default": "new-default-model",
         "description": "Available models: model-1, model-2, model-3"
       }
     }
   }
   ```

2. **For dropdown selection**, use enum:
   ```json
   {
     "properties": {
       "model": {
         "type": "string",
         "title": "Model",
         "enum": ["model-1", "model-2", "model-3"],
         "default": "model-1"
       }
     }
   }
   ```

3. **Run management script** for automated updates:
   ```bash
   python .claude/skills/adapter-ops/scripts/manage_models.py \
     --adapter llm \
     --provider openai \
     --action add-enum \
     --models "gpt-4-turbo,gpt-4o-mini"
   ```

### Editing Adapter Behavior

Common modifications:

1. **Add reasoning/thinking support**:
   - Add `enable_thinking` boolean field to JSON schema
   - Add conditional `thinking` config in `validate()` method
   - See `AnthropicLLMParameters` in `base1.py` for reference

2. **Add custom field mapping**:
   ```python
   @staticmethod
   def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
       # Map custom field names to expected names
       if "custom_field" in adapter_metadata:
           adapter_metadata["expected_field"] = adapter_metadata["custom_field"]
       # Continue validation...
   ```

3. **Add conditional fields in JSON schema**:
   ```json
   {
     "allOf": [
       {
         "if": { "properties": { "feature_enabled": { "const": true } } },
         "then": {
           "properties": { "feature_config": { "type": "string" } },
           "required": ["feature_config"]
         }
       }
     ]
   }
   ```

### Checking for Adapter Updates

Compare existing adapter schemas against known LiteLLM features to identify potential updates:

1. **Run the update checker**:
   ```bash
   # Check all adapters
   python .claude/skills/adapter-ops/scripts/check_adapter_updates.py

   # Check specific adapter type
   python .claude/skills/adapter-ops/scripts/check_adapter_updates.py --adapter llm
   python .claude/skills/adapter-ops/scripts/check_adapter_updates.py --adapter embedding

   # Check specific provider
   python .claude/skills/adapter-ops/scripts/check_adapter_updates.py --provider openai

   # Output as JSON
   python .claude/skills/adapter-ops/scripts/check_adapter_updates.py --json
   ```

2. **Review the report**:
   - 🟡 **NEEDS UPDATE**: Adapters with missing parameters or outdated features
   - ✅ **UP TO DATE**: Adapters matching known LiteLLM features
   - ❌ **ERRORS**: Adapters that couldn't be analyzed (missing schema, etc.)

3. **Common update types identified**:
   - **Missing parameters**: New configuration options (e.g., `dimensions` for embeddings)
   - **Reasoning/Thinking support**: Enable reasoning for models like o1, o3, Claude 3.7+, Magistral
   - **Outdated defaults**: Default models that have been superseded

4. **After identifying updates**:
   - Update JSON schema in `static/{provider}.json`
   - Update parameter class in `base1.py` if validation logic changes
   - Consult LiteLLM docs for implementation details (URLs provided in report)

5. **Update the feature database** (`check_adapter_updates.py`):
   - Edit `LITELLM_FEATURES` dict to add new providers or parameters
   - Keep `known_params`, `reasoning_models`, `thinking_models`, `latest_models` current
   - Add documentation URLs for reference

## Validation Checklist

Before submitting adapter changes:

- [ ] Adapter class inherits from correct parameter class AND `BaseAdapter`
- [ ] `get_id()` returns unique `{provider}|{uuid}` format
- [ ] `get_metadata()` returns dict with `name`, `version`, `adapter`, `description`, `is_active`
- [ ] `get_provider()` matches the static JSON filename (`static/{get_provider()}.json`)
- [ ] **CRITICAL: the model string produced by `validate_model()` resolves in LiteLLM's cost map** (see below)
- [ ] `get_adapter_type()` returns correct `AdapterTypes.LLM` or `AdapterTypes.EMBEDDING`
- [ ] JSON schema has `adapter_name` as required field
- [ ] `validate()` method adds correct model prefix
- [ ] `validate_model()` method handles prefix idempotently (doesn't double-prefix)
- [ ] All static methods decorated with `@staticmethod`
- [ ] Icon path follows pattern `/icons/adapter-icons/{Name}.png`

### Model Prefix Verification (MANDATORY)

Cost is looked up from the **validated model string**, not from `get_provider()`. The string
that `validate_model()` produces (e.g. `mistral/mistral-embed`) is passed straight to
`litellm.cost_per_token()`. If LiteLLM's cost map has no entry for it, the lookup raises, the
exception is swallowed, and usage records **$0**.

The lookup sites:

| Path | Site |
|------|------|
| LLM | `unstract/sdk1/src/unstract/sdk1/audit.py` — `cost_per_token(model=model_name)` |
| Embedding | `unstract/sdk1/src/unstract/sdk1/usage_handler.py` — `litellm.cost_per_token(...)` |

`model_name` is `self._cost_model or self.kwargs["model"]` — the prefixed string. Both call
sites catch every exception and fall back to `0.0`, so a miss is **silent**. It will not fail a
test, a build, or a run. The only symptom is revenue-affecting: zero-cost usage rows.

**Before implementing any adapter, verify the prefix resolves.** Use the pinned LiteLLM in the
sdk1 venv rather than curling upstream JSON — the pinned version is what actually runs:

```bash
cd unstract/sdk1 && uv run python -c "
import litellm
from litellm import cost_per_token

# 1. Does LiteLLM have a native provider for this vendor?
print([p for p in litellm.provider_list if 'YOUR_VENDOR' in str(p).lower()])

# 2. Which of its models are priced?
print([k for k in litellm.model_cost if k.lower().startswith('YOUR_PROVIDER/')])

# 3. Does the string your validate_model() emits actually resolve?
for m in ['YOUR_PROVIDER/some-model', 'custom_openai/some-model']:
    try:
        print(m, cost_per_token(model=m, prompt_tokens=1_000_000, completion_tokens=1_000_000))
    except Exception as e:
        print(m, 'RAISES', type(e).__name__, '=> cost silently recorded as 0.0')
"
```

**Branded OpenAI-compatible adapters: pick the right base class.**

Many vendors speak the OpenAI wire protocol, which tempts you to subclass
`OpenAICompatibleLLMParameters` and just pin `api_base`. But its `validate_model()`
unconditionally prepends `custom_openai/`, and **nothing** in LiteLLM's cost map is keyed that
way. That silently forfeits cost tracking.

| If… | Then | Cost tracking |
|-----|------|---------------|
| LiteLLM has a native provider for the vendor | Extend `BaseChatCompletionParameters`, emit `{provider}/{model}` — follow `OpenRouterLLMParameters` | ✅ resolves |
| LiteLLM has **no** priced models for the vendor | Extend `OpenAICompatibleLLMParameters`, pin `api_base` — follow `NvidiaBuildLLMParameters` | ⚠️ $0 either way, nothing forfeited |

`NvidiaBuildLLMParameters` is only a safe template because LiteLLM prices zero `nvidia_nim/`
chat models — there is no cost to lose. Do not copy that shape for a vendor LiteLLM *does*
price. Check first with the snippet above.

**What `get_provider()` is actually for:**

1. Resolving the static schema path — `{type}1/static/{get_provider()}.json` (case-sensitive `open()`).
2. The `provider` column on the usage row (`audit.py`) — metadata only, not used for pricing.

Keeping it equal to LiteLLM's `litellm_provider` value is still good hygiene, and matters when
you route natively (the prefix and the provider name coincide). But a correct `get_provider()`
does **not** on its own guarantee cost resolution — a branded adapter can return `"minimax"`,
match `litellm_provider` exactly, and still bill $0 because its model string carries the
`custom_openai/` prefix.

**Common provider names:**

| Display Name | `get_provider()` Value |
|--------------|------------------------|
| OpenAI | `openai` |
| Anthropic | `anthropic` |
| Azure OpenAI | `azure` |
| Azure AI Foundry | `azure_ai` |
| AWS Bedrock | `bedrock` |
| Google VertexAI | `vertex_ai` |
| Mistral | `mistral` |
| Ollama | `ollama` |

## Maintenance Workflow

Periodic maintenance to keep adapters current with LiteLLM features:

### Monthly Update Check

1. **Run the update checker**:
   ```bash
   python .claude/skills/adapter-ops/scripts/check_adapter_updates.py
   ```

2. **Review LiteLLM changelog** for new provider features:
   - https://github.com/BerriAI/litellm/releases

3. **Update feature database** in `check_adapter_updates.py`:
   - Add new `known_params` for each provider
   - Update `reasoning_models` and `thinking_models` lists
   - Update `latest_models` with current defaults

4. **Apply updates** following priority:
   - 🔴 **High**: Security or breaking changes
   - 🟡 **Medium**: New capabilities (reasoning, dimensions)
   - 🟢 **Low**: Model updates, documentation

### After LiteLLM Upgrade

When upgrading LiteLLM dependency:

1. Check for **API changes** in provider parameters
2. Verify **model prefix** requirements haven't changed
3. Test **thinking/reasoning** features still work
4. Update **default models** if deprecated

### Adding New Provider Support

When LiteLLM adds a new provider:

1. Check LiteLLM docs: `https://docs.litellm.ai/docs/providers/{provider}`
2. Add feature data to `check_adapter_updates.py`
3. Run init script to create adapter skeleton
4. Customize JSON schema and parameter class

## Reference Files

For detailed patterns and examples, see:
- `references/adapter_patterns.md` - Complete code patterns
- `references/json_schema_guide.md` - JSON schema patterns for UI
- `references/provider_capabilities.md` - Provider feature matrix
- `assets/templates/` - Ready-to-use templates

## Troubleshooting

### Adapter not appearing in list
- Verify class name ends with `LLMAdapter` or `EmbeddingAdapter`
- Check `is_active: True` in metadata
- Ensure file is in correct directory (`llm1/` or `embedding1/`)

### Validation errors
- Check parameter class fields match JSON schema required fields
- Verify `validate()` returns properly validated dict
- Ensure model prefix logic is idempotent

### Import errors
- Verify imports in adapter file match available classes in `base1.py`
- Check for circular imports (use `TYPE_CHECKING` guard)
