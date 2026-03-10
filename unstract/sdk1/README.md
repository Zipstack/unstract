<div align="center">
<img src="https://raw.githubusercontent.com/Zipstack/unstract-sdk/main/docs/assets/unstract_u_logo.png" style="height: 60px">

# Unstract SDK 1.x

The `unstract-sdk1` package helps with developing tools that are meant to be run on the Unstract platform. This includes
modules to help with tool development and execution, caching, making calls to LLMs / vectorDBs / embeddings .etc.
They also contain helper methods/classes to aid with other tasks such as indexing and auditing the LLM calls.

## Features

### Retry Configuration

The SDK automatically retries platform and prompt service calls on transient failures. Configure via environment variables (prefix: `PLATFORM_SERVICE_` or `PROMPT_SERVICE_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_RETRIES` | 3 | Maximum retry attempts |
| `BASE_DELAY` | 1.0 | Initial delay (seconds) |
| `MULTIPLIER` | 2.0 | Backoff multiplier |
| `JITTER` | true | Add random jitter (0-25%) |

**Retryable errors**: ConnectionError, Timeout, HTTPError (502/503/504), OSError (connection failures)

## Development

### Running Tests

Install test dependencies and run tests:

```bash
# Install dependencies
uv sync --group test

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/unstract/sdk1 --cov-report=html
```
