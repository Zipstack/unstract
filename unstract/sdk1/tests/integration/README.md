# Integration Tests for Unstract SDK1 LLM Adapters

This directory contains comprehensive integration tests for Unstract SDK1 LLM adapters using **pytest parametrization**. These tests focus on **real integration testing** with external services, ensuring that the adapters work correctly with actual API providers.

## Overview

The integration tests verify:
- Real API connections to LLM providers
- Prompt generation and response parsing
- Streaming vs non-streaming modes
- Rate limiting and retry logic
- Token counting and usage tracking
- Error handling for API failures
- Parameter validation (temperature, max_tokens, etc.)
- Provider-specific features

## Key Architecture Decision: Single Parameterized Test File

Instead of separate test files for each provider, we use **pytest parametrization** to run the same comprehensive test suite against all LLM providers. This approach:

✅ **Eliminates code duplication** - Write tests once, run for all providers
✅ **Ensures consistency** - All providers tested identically
✅ **Easy to maintain** - Update tests in one place
✅ **Leverages LiteLLM** - Uses the unified LLM interface
✅ **Configurable** - Add new providers by updating config only

## Test Coverage

### Supported LLM Providers

All providers are tested through a single test file (`test_llm.py`) with provider-specific configurations in `llm_test_config.py`:

| Provider | Configuration Key | Required Env Vars |
|----------|------------------|-------------------|
| OpenAI | `openai` | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| Azure OpenAI | `azure_openai` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_MODEL` |
| AWS Bedrock | `bedrock` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME`, `BEDROCK_MODEL` |
| Vertex AI | `vertexai` | `VERTEXAI_PROJECT`, `VERTEXAI_JSON_CREDENTIALS`, `VERTEXAI_MODEL` |
| Ollama | `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |
| Mistral AI | `mistral` | `MISTRAL_API_KEY`, `MISTRAL_MODEL` |
| Anyscale | `anyscale` | `ANYSCALE_API_KEY`, `ANYSCALE_MODEL` |

### Test Categories

Each provider is automatically tested for:

#### Core Functionality (8 tests per provider)
- ✅ `test_connection` - Verify adapter can connect
- ✅ `test_simple_completion` - Basic completion test
- ✅ `test_complex_completion` - Complex prompt test
- ✅ `test_streaming_completion` - Streaming response test
- ✅ `test_json_extraction` - JSON extraction test
- ✅ `test_custom_system_prompt` - Custom system prompt test
- ✅ `test_temperature_parameter` - Temperature settings test
- ✅ `test_max_tokens_parameter` - Token limits test

#### Metadata & Configuration (3 tests per provider)
- ✅ `test_get_model_name` - Model name retrieval
- ✅ `test_get_context_window_size` - Context window size
- ✅ `test_comprehensive_metadata_validation` - Full metadata validation

#### Stability & Performance (3 tests per provider)
- ✅ `test_multiple_completions_sequential` - Connection stability
- ✅ `test_reasoning_capability` - Reasoning test (math problem)
- ✅ `test_retry_logic_with_timeout` - Retry mechanism test
- ✅ `test_response_format_consistency` - Response consistency

#### Error Handling (2 tests per provider)
- ✅ `test_invalid_credentials_error_handling` - Authentication errors
- ✅ `test_empty_prompt_handling` - Edge case handling

**Total: 16 test methods × N configured providers**

## Setup

### 1. Environment Variables

Copy the sample environment file and configure your credentials:

```bash
cd unstract/sdk1/tests/integration
cp .env.test.sample .env.test
```

Edit `.env.test` and add your API credentials for the providers you want to test. **Only configure the services you plan to test** - tests will be automatically skipped if required environment variables are not set.

**⚠️ Important**: Never commit `.env.test` to version control!

### 2. Load Environment Variables

Before running tests, load the environment variables:

```bash
# Using export (bash/zsh)
export $(grep -v '^#' .env.test | xargs)

# Or source the file
source .env.test
```

### 3. Install Test Dependencies

Ensure you have the test dependencies installed:

```bash
cd backend/
uv sync --group dev
```

## Running Tests

### Run All LLM Integration Tests (All Providers)

```bash
cd backend/
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v
```

This will run all test methods for **all configured providers**.

### Run Tests for a Specific Provider

```bash
# OpenAI tests only (use brackets for exact match)
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "[openai]"

# Anthropic tests only
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "[anthropic]"

# Ollama tests only (local server)
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "[ollama]"

# Alternative: Exclude other providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "openai and not azure"
```

### Run a Specific Test Method Across All Providers

```bash
# Run only connection tests for all providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "connection"

# Run only streaming tests for all providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "streaming"

# Run only error handling tests for all providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py::TestLLMErrorHandling -v
```

### Run a Specific Test for a Specific Provider

```bash
# Run only connection test for OpenAI (exact match)
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "test_connection[openai]"

# Run only streaming test for Anthropic
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "test_streaming[anthropic]"

# Alternative: Combine filters
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "connection and [openai]"
```

### Run Tests with Coverage

```bash
uv run pytest ../unstract/sdk1/tests/integration/ --cov=unstract.sdk1.llm --cov-report=html -v
```

### Run Tests in Parallel (Faster)

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -n auto -v
```

## File Structure

```
integration/
├── __init__.py                 # Package initialization
├── llm_test_config.py          # Provider configurations (ADD NEW PROVIDERS HERE)
├── test_llm.py                 # Parameterized test suite
├── test_helpers.py             # Reusable test utilities
├── .env.test.sample            # Environment variable template
├── README.md                   # This file
└── QUICKSTART.md               # Quick start guide
```

### Key Files

#### `llm_test_config.py`
Defines provider configurations including:
- Adapter IDs
- Required environment variables
- Metadata builder functions
- Provider display names

**To add a new provider**: Add configuration to `PROVIDER_CONFIGS` dictionary.

#### `test_llm.py`
Contains the parameterized test suite with two test classes:
- `TestLLMAdapters` - Core functionality tests
- `TestLLMErrorHandling` - Error handling tests

All tests are automatically parametrized to run for each configured provider.

## Adding a New Provider

To add support for a new LLM provider, you only need to update `llm_test_config.py`:

```python
# 1. Create metadata builder function
def build_new_provider_metadata() -> dict[str, Any]:
    """Build NewProvider adapter metadata."""
    return {
        "model": os.getenv("NEW_PROVIDER_MODEL"),
        "api_key": os.getenv("NEW_PROVIDER_API_KEY"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }

# 2. Add to PROVIDER_CONFIGS dictionary
PROVIDER_CONFIGS = {
    # ... existing providers ...
    "new_provider": LLMProviderConfig(
        provider_name="New Provider",
        adapter_id="new_provider|unique-uuid-here",
        required_env_vars=["NEW_PROVIDER_API_KEY", "NEW_PROVIDER_MODEL"],
        metadata_builder=build_new_provider_metadata,
    ),
}
```

That's it! The test suite will automatically run all tests for the new provider.

## Example Test Run Output

```bash
$ uv run pytest test_llm.py -v

test_llm.py::TestLLMAdapters::test_connection[openai]
✅ OpenAI adapter successfully established connection
PASSED                                                [ 6%]

test_llm.py::TestLLMAdapters::test_connection[anthropic]
✅ Anthropic adapter successfully established connection
PASSED                                                [12%]

test_llm.py::TestLLMAdapters::test_simple_completion[openai]
✅ OpenAI: Successfully completed simple prompt
   Response: Paris is the capital of France...
PASSED                                                [18%]

test_llm.py::TestLLMAdapters::test_simple_completion[anthropic]
✅ Anthropic: Successfully completed simple prompt
   Response: Paris is the capital of France...
PASSED                                                [25%]

test_llm.py::TestLLMAdapters::test_streaming_completion[openai]
✅ OpenAI: Successfully streamed completion in 15 chunks
PASSED                                                [31%]

... (tests continue for all providers and all test methods)

==================== 128 passed in 145.23s ====================
```

### Skipped Tests

Tests are automatically skipped if environment variables aren't configured:

```
test_llm.py::TestLLMAdapters::test_connection[azure_openai]
SKIPPED (Required Azure OpenAI environment variables not set...)

test_llm.py::TestLLMAdapters::test_connection[vertexai]
SKIPPED (Required Vertex AI environment variables not set...)
```

## Mock Strategy

These integration tests follow a specific mocking philosophy:

✅ **DO Mock:**
- Platform dependencies (UserContext, workflow objects)
- Django model instances
- Internal data retrieval methods

❌ **DO NOT Mock:**
- External API calls to LLM providers
- Adapter instances
- Service operations
- Network communication

This ensures we test **real integration** with external services while isolating platform-specific dependencies.

## Environment Variable Reference

See `.env.test.sample` for the complete list of environment variables with examples and descriptions for all providers.

### Quick Reference

#### OpenAI
```bash
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o-mini"
```

#### Anthropic
```bash
ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_MODEL="claude-3-5-sonnet-20241022"
```

#### Azure OpenAI
```bash
AZURE_OPENAI_API_KEY="your-key"
AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
AZURE_OPENAI_MODEL="gpt-4-deployment"
AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

#### Ollama (Local)
```bash
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="llama3.2"
```

For complete environment variable documentation, see `.env.test.sample`.

## Cost Considerations

⚠️ **Important**: Running these integration tests will make real API calls to external services, which may incur costs.

**Cost Management Tips:**
1. Start with smaller models (gpt-4o-mini, claude-3-haiku)
2. Use local Ollama for development/testing (free)
3. Run specific test subsets: `pytest -k "connection"` (cheapest)
4. Set up billing alerts on provider accounts
5. Use `-k "not reasoning"` to skip expensive reasoning tests

**Estimated Costs per Full Test Run:**
- OpenAI (gpt-4o-mini): ~$0.10-0.20
- Anthropic (claude-haiku): ~$0.05-0.15
- Ollama (local): $0 (free)

## Troubleshooting

### All tests are skipped

**Cause**: Required environment variables are not set.

**Solution**:
```bash
# 1. Check .env.test exists
ls -la .env.test

# 2. Load environment variables
export $(grep -v '^#' .env.test | xargs)

# 3. Verify they're loaded
echo $OPENAI_API_KEY
```

### Authentication errors

**Cause**: Invalid or expired credentials.

**Solution**:
1. Verify your API keys are correct in `.env.test`
2. Check that you have sufficient quota/credits
3. Ensure credentials have necessary permissions

### Ollama connection refused

**Cause**: Ollama server is not running.

**Solution**:
```bash
# Start Ollama server
ollama serve

# Pull the model
ollama pull llama3.2

# Verify it's running
curl http://localhost:11434/api/tags
```

### Import errors

**Cause**: Dependencies not installed.

**Solution**:
```bash
cd backend/
uv sync --group dev
```

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: LLM Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd backend
          pip install uv
          uv sync --group dev
      - name: Run integration tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_MODEL: "gpt-4o-mini"
        run: |
          cd backend
          uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "openai"
```

## Helper Utilities

The `test_helpers.py` module provides utilities:

- `TestHelpers.verify_response_schema()` - Validate response structure
- `TestHelpers.verify_json_structure()` - Check for valid JSON
- `TestHelpers.retry_with_backoff()` - Retry with exponential backoff
- `TestHelpers.measure_execution_time()` - Benchmark performance
- `PerformanceBenchmark` - Context manager for timing operations

Example usage:

```python
from unstract.sdk1.tests.integration.test_helpers import PerformanceBenchmark

with PerformanceBenchmark("LLM Completion"):
    result = llm.complete(prompt)
# Output: ⏱️  LLM Completion took 2.34 seconds
```

## Benefits of Parameterized Approach

### Before (8 separate files, ~900 lines each)
```
test_llm_openai.py        (900 lines)
test_llm_anthropic.py     (900 lines)
test_llm_azure_openai.py  (900 lines)
test_llm_bedrock.py       (900 lines)
test_llm_vertexai.py      (900 lines)
test_llm_ollama.py        (900 lines)
test_llm_mistral.py       (900 lines)
test_llm_anyscale.py      (900 lines)
-------------------------------------------
Total: ~7,200 lines with 95% duplication
```

### After (1 test file + 1 config file)
```
test_llm.py            (~600 lines)
llm_test_config.py     (~250 lines)
-------------------------------------------
Total: ~850 lines, zero duplication
```

**Benefits:**
- 🎯 **90% reduction in code** (850 vs 7,200 lines)
- ✅ **Single source of truth** for test logic
- 🔧 **Easy maintenance** - update tests once
- 🚀 **Easy to extend** - add provider in config only
- 📊 **Consistent testing** - identical tests for all providers
- 🧪 **Leverages pytest** - built-in parametrization features

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review QUICKSTART.md for setup guidance
3. Check provider documentation for API-specific issues
4. Open an issue on GitHub with test logs and environment details

## Related Documentation

- **QUICKSTART.md** - Get running in 5 minutes
- **test_helpers.py** - Utility functions documentation
- **.env.test.sample** - Complete environment variable reference
- **Unstract Docs** - https://docs.unstract.com
