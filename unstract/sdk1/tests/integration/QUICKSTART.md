# Quick Start Guide - SDK1 LLM Integration Tests

This guide will help you quickly set up and run the **parameterized** integration tests for Unstract SDK1 LLM adapters.

## What's Special About These Tests?

Unlike traditional test suites with separate files for each provider, these tests use **pytest parametrization** to run the same comprehensive test suite against ALL LLM providers using a single test file. This means:

- ✅ Write tests once, test all providers
- ✅ Add new providers by just updating configuration
- ✅ Consistent testing across all LLM providers
- ✅ 90% less code compared to separate files

## Prerequisites

- Python 3.11+
- Active API credentials for at least one LLM provider
- Internet connection (except for Ollama local tests)

## 5-Minute Setup

### Step 1: Navigate to Integration Tests Directory

```bash
cd /path/to/unstract/unstract/sdk1/tests/integration
```

### Step 2: Create Environment Configuration

```bash
# Copy sample environment file
cp .env.test.sample .env.test

# Edit with your credentials (use your preferred editor)
nano .env.test  # or vim, code, etc.
```

### Step 3: Add Your API Credentials

At minimum, add credentials for one provider. For example, for OpenAI:

```bash
# In .env.test
OPENAI_API_KEY="sk-your-actual-key-here"
OPENAI_MODEL="gpt-4o-mini"
```

### Step 4: Load Environment Variables

```bash
# Export all environment variables
export $(grep -v '^#' .env.test | xargs)

# Verify they're loaded
echo $OPENAI_API_KEY  # Should print your key
```

### Step 5: Run Tests

```bash
# Navigate to backend directory
cd ../../../../backend/

# Run all integration tests for all configured providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v

# Or run tests for a specific provider only (use brackets for exact match)
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "[openai]"
```

## Common Test Scenarios

### Scenario 1: Test OpenAI Only (Recommended for First Run)

```bash
# 1. Set only OpenAI credentials in .env.test
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o-mini"

# 2. Load environment
export $(grep -v '^#' .env.test | xargs)

# 3. Run OpenAI tests
cd backend/
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "openai"
```

**Expected output:**
```
test_llm.py::TestLLMAdapters::test_connection[openai] PASSED
test_llm.py::TestLLMAdapters::test_simple_completion[openai] PASSED
test_llm.py::TestLLMAdapters::test_streaming_completion[openai] PASSED
... (16 tests for OpenAI)
==================== 16 passed in 25.34s ====================
```

### Scenario 2: Test Local Ollama (Free, No API Costs)

```bash
# 1. Install and start Ollama
# Download from https://ollama.ai
ollama serve

# 2. Pull a model
ollama pull llama3.2

# 3. Set Ollama configuration in .env.test
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="llama3.2"

# 4. Run Ollama tests
export $(grep -v '^#' .env.test | xargs)
cd backend/
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "ollama"
```

### Scenario 3: Test Multiple Providers Simultaneously

```bash
# 1. Configure multiple providers in .env.test
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o-mini"

ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_MODEL="claude-3-5-sonnet-20241022"

OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="llama3.2"

# 2. Load environment
export $(grep -v '^#' .env.test | xargs)

# 3. Run all tests - will test ALL configured providers!
cd backend/
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v
```

**Expected output:**
```
test_llm.py::TestLLMAdapters::test_connection[openai] PASSED
test_llm.py::TestLLMAdapters::test_connection[anthropic] PASSED
test_llm.py::TestLLMAdapters::test_connection[ollama] PASSED
test_llm.py::TestLLMAdapters::test_simple_completion[openai] PASSED
test_llm.py::TestLLMAdapters::test_simple_completion[anthropic] PASSED
test_llm.py::TestLLMAdapters::test_simple_completion[ollama] PASSED
... (48 tests total for 3 providers × 16 test methods)
==================== 48 passed in 75.45s ====================
```

### Scenario 4: Test Specific Functionality Across All Providers

```bash
# Test only streaming for all configured providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "streaming"

# Test only connection for all configured providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "connection"

# Test only error handling for all configured providers
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py::TestLLMErrorHandling -v
```

## Understanding Parameterized Tests

### How It Works

The single `test_llm.py` file contains test methods that are **automatically run** for each configured provider:

```python
@pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
def test_connection(self, provider_key: str) -> None:
    """Test connection for ALL providers."""
    # This same test runs for openai, anthropic, ollama, etc.
```

When you run the tests, pytest automatically:
1. Detects which providers have required env vars set
2. Runs each test method for each configured provider
3. Shows individual results per provider

### Test Naming Convention

Test names follow the pattern: `test_method[provider_key]`

Examples:
- `test_connection[openai]` - Connection test for OpenAI
- `test_connection[anthropic]` - Connection test for Anthropic
- `test_streaming_completion[ollama]` - Streaming test for Ollama

This makes it easy to identify which provider/test combination failed.

## Expected Output Examples

### Successful Test Run

```
test_llm.py::TestLLMAdapters::test_connection[openai]
✅ OpenAI adapter successfully established connection
PASSED                                                [  6%]

test_llm.py::TestLLMAdapters::test_simple_completion[openai]
✅ OpenAI: Successfully completed simple prompt
   Response: Paris is the capital of France...
PASSED                                                [ 12%]

test_llm.py::TestLLMAdapters::test_streaming_completion[openai]
✅ OpenAI: Successfully streamed completion in 15 chunks
PASSED                                                [ 18%]

==================== 16 passed in 25.34s ====================
```

### Skipped Tests (Missing Credentials)

```
test_llm.py::TestLLMAdapters::test_connection[azure_openai]
SKIPPED (Required Azure OpenAI environment variables not set...)

test_llm.py::TestLLMAdapters::test_connection[vertexai]
SKIPPED (Required Vertex AI environment variables not set...)

==================== 16 passed, 32 skipped in 25.34s ====================
```

This is normal and expected! Tests are automatically skipped if credentials aren't configured.

## Troubleshooting Common Issues

### Issue: "Module not found: unstract.sdk1"

**Solution:**
```bash
# Make sure you're in the backend directory
cd backend/

# Install dependencies
uv sync --group dev
```

### Issue: "All tests are skipped"

**Solution:**
```bash
# Verify environment variables are loaded
echo $OPENAI_API_KEY

# If empty, reload:
cd unstract/sdk1/tests/integration
export $(grep -v '^#' .env.test | xargs)
```

### Issue: "Authentication error / 401 Unauthorized"

**Solution:**
- Double-check your API key is correct
- Verify the key is active and not expired
- Check you have sufficient credits/quota
- Ensure no extra spaces in the .env.test file

### Issue: "No tests collected" or "pytest not found"

**Solution:**
```bash
# Ensure you're running from backend directory
cd backend/

# Use uv run to ensure correct environment
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v
```

## Running Specific Test Combinations

### Specific Provider + Specific Test

```bash
# Only streaming test for OpenAI
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "openai and streaming"

# Only connection test for Anthropic
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "anthropic and connection"
```

### Multiple Providers, Specific Test

```bash
# Streaming test for both OpenAI and Anthropic
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "streaming and (openai or anthropic)"
```

### All Tests Except Certain Ones

```bash
# All tests except reasoning (saves tokens/costs)
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "not reasoning"

# All tests except error handling
uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v -k "not TestLLMErrorHandling"
```

## Adding a New Provider

Want to test a new LLM provider? Just edit `llm_test_config.py`:

```python
# 1. Add metadata builder function
def build_new_provider_metadata() -> dict[str, Any]:
    return {
        "model": os.getenv("NEW_PROVIDER_MODEL"),
        "api_key": os.getenv("NEW_PROVIDER_API_KEY"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }

# 2. Add to PROVIDER_CONFIGS
PROVIDER_CONFIGS = {
    # ... existing providers ...
    "new_provider": LLMProviderConfig(
        provider_name="New Provider",
        adapter_id="new_provider|uuid-here",
        required_env_vars=["NEW_PROVIDER_API_KEY", "NEW_PROVIDER_MODEL"],
        metadata_builder=build_new_provider_metadata,
    ),
}
```

That's it! The test suite automatically picks it up and runs all 16 tests for your new provider.

## Cost Management Tips

⚠️ These tests make real API calls and may incur costs!

### Minimize Costs

1. **Start with free/cheap options:**
   ```bash
   # Ollama - completely free (local)
   uv run pytest -k "ollama" -v

   # OpenAI gpt-4o-mini - cheapest OpenAI model
   OPENAI_MODEL="gpt-4o-mini"
   ```

2. **Run only connection tests first** (minimal tokens):
   ```bash
   uv run pytest -k "connection" -v
   ```

3. **Skip expensive tests:**
   ```bash
   # Skip reasoning tests which use more tokens
   uv run pytest -k "not reasoning" -v
   ```

4. **Test one provider at a time:**
   ```bash
   uv run pytest -k "openai" -v
   ```

## Next Steps

Once you've successfully run the basic tests:

1. **Read the full documentation:** See `README.md` for comprehensive details
2. **Configure more providers:** Add more services to `.env.test`
3. **Understand the architecture:** Review `llm_test_config.py` to see how providers are configured
4. **Customize tests:** Modify `test_llm.py` for your specific needs
5. **Integrate with CI/CD:** Use in your automated testing pipeline

## Quick Command Reference

```bash
# Run all tests for all configured providers
uv run pytest test_llm.py -v

# Run tests for specific provider
uv run pytest test_llm.py -v -k "openai"

# Run specific test across all providers
uv run pytest test_llm.py -v -k "connection"

# Run specific test for specific provider
uv run pytest test_llm.py -v -k "openai and connection"

# Run with output capture disabled (see print statements)
uv run pytest test_llm.py -v -s

# Run in parallel (faster, requires pytest-xdist)
uv run pytest test_llm.py -v -n auto
```

## Summary Checklist

- [ ] Created `.env.test` from `.env.test.sample`
- [ ] Added API credentials for at least one provider
- [ ] Loaded environment variables with `export $(grep -v '^#' .env.test | xargs)`
- [ ] Navigated to `backend/` directory
- [ ] Ran tests with `uv run pytest ../unstract/sdk1/tests/integration/test_llm.py -v`
- [ ] Verified tests pass (or are appropriately skipped)
- [ ] Understood how parametrization works
- [ ] Ready to add more providers or customize tests

Congratulations! You're now running comprehensive parameterized integration tests for Unstract SDK1 LLM adapters! 🎉

The beauty of this approach: **Add a new provider in 5 lines of config, get 16 tests automatically!**
