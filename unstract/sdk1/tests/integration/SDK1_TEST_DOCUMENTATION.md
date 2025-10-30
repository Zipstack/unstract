# Unstract SDK1 Testing Documentation

**Version**: v1.0.0
**Purpose**: Comprehensive reference for writing integration tests for SDK1 components
**Audience**: Test developers, automation engineers, QA teams

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Adapter System](#adapter-system)
4. [Test Patterns](#test-patterns)
5. [Environment Configuration](#environment-configuration)
6. [Common Test Scenarios](#common-test-scenarios)

---

## Architecture Overview

### SDK1 Structure

```
unstract/sdk1/
├── src/unstract/sdk1/
│   ├── llm.py              # LLM interface (LiteLLM-powered)
│   ├── embedding.py        # Embedding interface (LiteLLM-powered)
│   ├── vector_db.py        # Vector database operations
│   ├── x2txt.py            # Text extraction from documents
│   ├── platform.py         # Platform integration helpers
│   ├── exceptions.py       # SDK-specific exceptions
│   ├── constants.py        # SDK constants and enums
│   └── adapters/
│       ├── llm1/           # LLM adapters
│       ├── embedding1/     # Embedding adapters
│       ├── vectordb/       # Vector DB adapters
│       ├── x2text/         # Text extraction adapters
│       └── ocr/            # OCR adapters
└── tests/
    └── integration/        # Integration test suite
```

### Design Principles

1. **Adapter Pattern**: All external services accessed through adapters
2. **LiteLLM Integration**: Unified interface for LLM and Embedding operations
3. **Platform-Aware**: Optional integration with Unstract Platform
4. **Tool-Based Architecture**: BaseTool provides context for operations

---

## Core Components

### 1. LLM Class (`llm.py`)

**Purpose**: Unified interface for Large Language Models

**Key Features**:
- LiteLLM-powered multi-provider support
- Streaming and non-streaming completions
- JSON mode support with validation
- Token counting and usage tracking
- Metrics capture capabilities

**Initialization Patterns**:

```python
# Pattern 1: Direct adapter configuration (for testing)
from unstract.sdk1.llm import LLM

llm = LLM(
    adapter_id="openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
    adapter_metadata={
        "model": "gpt-4o-mini",
        "api_key": "sk-...",
        "api_base": "https://api.openai.com/v1",
        "temperature": 0.1,
        "max_tokens": 1000
    }
)

# Pattern 2: Platform-integrated (production)
llm = LLM(
    adapter_instance_id="instance-uuid",
    tool=tool_instance
)
```

**Core Methods**:

| Method | Purpose | Returns | Test Importance |
|--------|---------|---------|----------------|
| `complete()` | Generate text completion | `str` | **Critical** - Core functionality |
| `complete_with_json()` | JSON-structured completion | `dict` | **Critical** - Structured outputs |
| `stream_complete()` | Stream completion tokens | `Generator[str]` | **High** - Real-time apps |
| `count_tokens()` | Count tokens in text | `int` | **Medium** - Cost estimation |
| `test_connection()` | Verify adapter connectivity | `bool` | **Critical** - Connection validation |
| `get_context_window_size()` | Get model's context limit | `int` | **Medium** - Capacity planning |

**Exception Handling**:
- `LLMError`: General LLM operation failures
- `SdkError`: SDK initialization or configuration errors
- `ValidationError`: Invalid adapter metadata

---

### 2. Embedding Class (`embedding.py`)

**Purpose**: Unified interface for text embeddings

**Key Features**:
- LiteLLM-powered embedding generation
- Batch and single text processing
- Async operation support
- Automatic dimension detection

**Initialization Patterns**:

```python
from unstract.sdk1.embedding import Embedding

# Direct configuration
embedding = Embedding(
    adapter_id="openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151",
    adapter_metadata={
        "model": "text-embedding-3-small",
        "api_key": "sk-...",
        "api_base": "https://api.openai.com/v1",
        "temperature": 0.0
    }
)
```

**Core Methods**:

| Method | Purpose | Returns | Test Importance |
|--------|---------|---------|----------------|
| `get_embedding()` | Generate single embedding | `list[float]` | **Critical** - Core sync operation |
| `get_embeddings()` | Generate batch embeddings | `list[list[float]]` | **Critical** - Batch processing |
| `get_aembedding()` | Async single embedding | `list[float]` | **High** - Async workflows |
| `get_aembeddings()` | Async batch embeddings | `list[list[float]]` | **High** - Async batch ops |
| `test_connection()` | Verify adapter connectivity | `bool` | **Critical** - Connection validation |

**Properties**:
- `_length`: Embedding dimension (auto-detected on init)

**Companion Class**: `EmbeddingCompat` - LlamaIndex compatibility wrapper

---

### 3. VectorDB Class (`vector_db.py`)

**Purpose**: Vector database operations for document indexing and retrieval

**Key Features**:
- LlamaIndex VectorStore integration
- Multi-provider support (Pinecone, Weaviate, Qdrant, etc.)
- Automatic embedding dimension handling
- Organization-scoped collections

**Initialization**:

```python
from unstract.sdk1.vector_db import VectorDB
from unstract.sdk1.embedding import EmbeddingCompat

# Requires tool instance and embedding
vector_db = VectorDB(
    tool=tool_instance,
    adapter_instance_id="vectordb-instance-uuid",
    embedding=embedding_compat_instance
)
```

**Core Methods**:

| Method | Purpose | Test Importance |
|--------|---------|----------------|
| `add_document()` | Index document with metadata | **Critical** |
| `add_documents()` | Batch document indexing | **Critical** |
| `query()` | Similarity search | **Critical** |
| `delete_document()` | Remove document | **High** |
| `get_vector_store()` | Get underlying VectorStore | **Medium** |

**Dependencies**:
- Requires `BaseTool` instance (provides platform context)
- Requires `EmbeddingCompat` instance (for vectorization)

---

### 4. X2Text Class (`x2txt.py`)

**Purpose**: Text extraction from various document formats

**Key Features**:
- Multi-format support (PDF, DOCX, images, etc.)
- Adapter-based extraction (LLMWhisperer, LlamaParse, etc.)
- File storage integration
- Audit trail support

**Initialization**:

```python
from unstract.sdk1.x2txt import X2Text

x2text = X2Text(
    tool=tool_instance,
    adapter_instance_id="x2text-instance-uuid",
    usage_kwargs={}
)
```

**Core Methods**:

| Method | Purpose | Returns | Test Importance |
|--------|---------|---------|----------------|
| `process()` | Extract text from file | `TextExtractionResult` | **Critical** |
| `extract_as_pdf()` | Extract to PDF output | `bytes` | **High** |

**File Storage Integration**:
- Works with `FileStorage` abstraction
- Supports local, S3, Azure Blob, etc.

---

## Adapter System

### Adapter Architecture

All external services are accessed through **adapters** that implement a common interface.

### Adapter Types

#### 1. LLM Adapters (`adapters/llm1/`)

**Supported Providers**:
- OpenAI: `openai|502ecf49-e47c-445c-9907-6d4b90c5cd17`
- Anthropic: `anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203`
- Azure OpenAI: `azureopenai|dd8a2e37-8319-4d9f-8a8f-be41f07b3f99`
- AWS Bedrock: `bedrock|8d18571f-5e96-4505-bd28-ad0379c64064`
- Vertex AI: `vertexai|ba80fc7b-ad08-4b36-ab0f-b92e0b3915b4`
- Ollama: `ollama|f88c2c3d-f6e0-455f-aa32-3f4ca4a65c2b`
- Mistral: `mistral|7fa87c83-fb88-4504-8711-4d7fd9b5b45f`
- Anyscale: `anyscale|2dbfa1f9-1b9f-41b3-a4ed-7d6e6d14a28c`

**Metadata Structure**:
```python
{
    "model": str,           # Model identifier
    "api_key": str,         # API authentication key
    "api_base": str,        # Optional: Custom endpoint
    "temperature": float,   # Generation randomness (0.0-1.0)
    "max_tokens": int,      # Maximum output tokens
    # Provider-specific fields
}
```

#### 2. Embedding Adapters (`adapters/embedding1/`)

**Supported Providers**:
- OpenAI: `openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151`
- Azure OpenAI: `azureopenai|9770f3f6-f8ba-4fa0-bb3a-bef48a00e66f`
- AWS Bedrock: `bedrock|88199741-8d7e-4e8c-9d92-d76b0dc20c91`
- Vertex AI: `vertexai|457a256b-e74f-4251-98a0-8864aafb42a5`
- Ollama: `ollama|d58d7080-55a9-4542-becd-8433528e127b`

**Metadata Structure**:
```python
{
    "model": str,           # Embedding model identifier
    "api_key": str,         # API authentication key
    "api_base": str,        # Optional: Custom endpoint
    "temperature": float,   # Usually 0.0 for embeddings
    # Provider-specific fields
}
```

#### 3. VectorDB Adapters (`adapters/vectordb/`)

**Supported Providers**:
- Pinecone
- Weaviate
- Qdrant
- Milvus
- ChromaDB
- And more...

**Metadata Structure** (Provider-specific):
```python
# Example: Pinecone
{
    "api_key": str,
    "environment": str,
    "index_name": str
}

# Example: Weaviate
{
    "url": str,
    "api_key": str,
    "class_name": str
}
```

#### 4. X2Text Adapters (`adapters/x2text/`)

**Supported Extractors**:
- LLMWhisperer v2
- LlamaParse
- Unstructured Enterprise
- No-op (passthrough)

---

## Test Patterns

### Pattern 1: Parameterized Provider Testing

**Use Case**: Test same functionality across all providers

```python
import pytest
from unstract.sdk1.llm import LLM
from llm_test_config import PROVIDER_CONFIGS, get_available_providers

AVAILABLE_PROVIDERS = get_available_providers()

class TestLLMAdapters:
    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_connection(self, provider_key: str):
        config = PROVIDER_CONFIGS[provider_key]

        llm = LLM(
            adapter_id=config.adapter_id,
            adapter_metadata=config.build_metadata()
        )

        result = llm.test_connection()
        assert result is True
```

**Benefits**:
- Single test implementation for all providers
- Easy to add new providers
- Consistent test coverage

---

### Pattern 2: Environment-Based Configuration

**Use Case**: Skip tests when credentials unavailable

```python
class ProviderConfig:
    def __init__(self, provider_name, adapter_id, required_env_vars, metadata_builder):
        self.provider_name = provider_name
        self.adapter_id = adapter_id
        self.required_env_vars = required_env_vars
        self.metadata_builder = metadata_builder

    def should_skip(self) -> tuple[bool, str]:
        missing = [var for var in self.required_env_vars if not os.getenv(var)]
        if missing:
            return True, f"Missing env vars: {', '.join(missing)}"
        return False, ""
```

**Benefits**:
- Tests auto-skip when not configured
- Clear skip messages guide setup
- No hardcoded credentials

---

### Pattern 3: Real Integration Testing

**Principle**: Test against actual APIs, not mocks

```python
def test_single_completion():
    """Test real API call with actual LLM."""
    config = PROVIDER_CONFIGS["openai"]

    llm = LLM(
        adapter_id=config.adapter_id,
        adapter_metadata=config.build_metadata()
    )

    # Real API call
    result = llm.complete("What is 2+2?")

    # Verify real response
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0
```

**What to Mock**:
- ✅ Django/Platform dependencies (not external services)
- ✅ File system operations (when testing logic)
- ✅ Database connections (when testing SDK logic)

**What NOT to Mock**:
- ❌ LLM API calls (defeats integration testing purpose)
- ❌ Embedding API calls
- ❌ Vector DB operations
- ❌ Text extraction services

---

### Pattern 4: Async Operation Testing

**Use Case**: Test async methods with asyncio

```python
import asyncio

def test_async_embedding():
    embedding = Embedding(
        adapter_id=config.adapter_id,
        adapter_metadata=config.build_metadata()
    )

    async def get_async():
        return await embedding.get_aembedding("Test text")

    result = asyncio.run(get_async())

    assert result is not None
    assert isinstance(result, list)
    assert len(result) > 0
```

---

### Pattern 5: Error Handling Validation

**Use Case**: Verify proper error handling

```python
def test_invalid_credentials():
    metadata = config.build_metadata()
    metadata["api_key"] = "invalid-key-12345"

    llm = LLM(
        adapter_id=config.adapter_id,
        adapter_metadata=metadata
    )

    with pytest.raises(Exception) as exc_info:
        llm.complete("Test")

    error_message = str(exc_info.value).lower()
    assert any(keyword in error_message
               for keyword in ["api", "auth", "401", "403"])
```

---

## Environment Configuration

### Required Environment Variables

#### LLM Tests

```bash
# OpenAI
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o-mini"
OPENAI_API_BASE="https://api.openai.com/v1"

# Anthropic
ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_MODEL="claude-3-5-sonnet-20241022"

# Azure OpenAI
AZURE_OPENAI_API_KEY="..."
AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
AZURE_OPENAI_MODEL="gpt-4-deployment-name"
AZURE_OPENAI_API_VERSION="2024-02-15-preview"

# AWS Bedrock
AWS_ACCESS_KEY_ID="..."
AWS_SECRET_ACCESS_KEY="..."
AWS_REGION_NAME="us-east-1"
BEDROCK_MODEL="anthropic.claude-3-sonnet-20240229-v1:0"

# Vertex AI
VERTEXAI_PROJECT="your-gcp-project-id"
VERTEXAI_JSON_CREDENTIALS="/path/to/service-account.json"
VERTEXAI_MODEL="gemini-1.5-flash"

# Ollama (Local)
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="llama3.2"
```

#### Embedding Tests

```bash
# OpenAI Embeddings
OPENAI_EMBEDDING_API_KEY="sk-..."
OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
OPENAI_EMBEDDING_API_BASE="https://api.openai.com/v1"

# Azure OpenAI Embeddings
AZURE_OPENAI_EMBEDDING_API_KEY="..."
AZURE_OPENAI_EMBEDDING_ENDPOINT="https://your-resource.openai.azure.com"
AZURE_OPENAI_EMBEDDING_MODEL="text-embedding-ada-002"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME="your-deployment-name"
AZURE_OPENAI_EMBEDDING_API_VERSION="2024-02-15-preview"

# AWS Bedrock Embeddings
AWS_EMBEDDING_ACCESS_KEY_ID="..."
AWS_EMBEDDING_SECRET_ACCESS_KEY="..."
AWS_EMBEDDING_REGION_NAME="us-east-1"
BEDROCK_EMBEDDING_MODEL="amazon.titan-embed-text-v1"

# Vertex AI Embeddings
VERTEXAI_EMBEDDING_PROJECT="your-gcp-project-id"
VERTEXAI_EMBEDDING_JSON_CREDENTIALS="/path/to/service-account.json"
VERTEXAI_EMBEDDING_MODEL="text-embedding-004"

# Ollama Embeddings
OLLAMA_EMBEDDING_BASE_URL="http://localhost:11434"
OLLAMA_EMBEDDING_MODEL="nomic-embed-text"
```

### Setup Process

```bash
# 1. Copy sample environment file
cd unstract/sdk1/tests/integration
cp .env.test.sample .env.test

# 2. Edit .env.test with your credentials
nano .env.test

# 3. Load environment variables
source .env.test

# 4. Run tests
pytest test_llm.py -v
pytest test_embedding.py -v
```

---

## Common Test Scenarios

### Scenario 1: Basic LLM Completion

```python
def test_llm_basic_completion():
    """Test basic text completion functionality."""
    llm = LLM(
        adapter_id="openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
        adapter_metadata={
            "model": "gpt-4o-mini",
            "api_key": os.getenv("OPENAI_API_KEY"),
            "temperature": 0.1,
            "max_tokens": 100
        }
    )

    result = llm.complete("What is the capital of France?")

    assert result is not None
    assert "Paris" in result
```

### Scenario 2: JSON Mode Output

```python
def test_llm_json_output():
    """Test JSON-structured output."""
    llm = LLM(
        adapter_id="openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
        adapter_metadata={
            "model": "gpt-4o-mini",
            "api_key": os.getenv("OPENAI_API_KEY"),
            "temperature": 0.0
        }
    )

    prompt = "Extract the name and age: John is 25 years old"
    result = llm.complete_with_json(prompt)

    assert isinstance(result, dict)
    assert "name" in result or "Name" in result
    assert "age" in result or "Age" in result
```

### Scenario 3: Streaming Completion

```python
def test_llm_streaming():
    """Test streaming text generation."""
    llm = LLM(
        adapter_id="openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
        adapter_metadata={
            "model": "gpt-4o-mini",
            "api_key": os.getenv("OPENAI_API_KEY")
        }
    )

    chunks = []
    for chunk in llm.stream_complete("Count from 1 to 5"):
        chunks.append(chunk)

    full_text = "".join(chunks)
    assert len(chunks) > 1  # Multiple chunks
    assert len(full_text) > 0
```

### Scenario 4: Embedding Similarity

```python
def test_embedding_similarity():
    """Test that similar texts have similar embeddings."""
    embedding = Embedding(
        adapter_id="openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151",
        adapter_metadata={
            "model": "text-embedding-3-small",
            "api_key": os.getenv("OPENAI_EMBEDDING_API_KEY")
        }
    )

    text1 = "The cat sat on the mat"
    text2 = "A cat was sitting on a mat"
    text3 = "Quantum mechanics is complex"

    emb1 = embedding.get_embedding(text1)
    emb2 = embedding.get_embedding(text2)
    emb3 = embedding.get_embedding(text3)

    # Cosine similarity
    def cosine_similarity(a, b):
        import math
        dot = sum(x*y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(x*x for x in b))
        return dot / (norm_a * norm_b)

    sim_12 = cosine_similarity(emb1, emb2)
    sim_13 = cosine_similarity(emb1, emb3)

    assert sim_12 > sim_13  # Similar texts more similar
```

### Scenario 5: Batch Embedding

```python
def test_batch_embeddings():
    """Test batch embedding generation."""
    embedding = Embedding(
        adapter_id="openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151",
        adapter_metadata={
            "model": "text-embedding-3-small",
            "api_key": os.getenv("OPENAI_EMBEDDING_API_KEY")
        }
    )

    texts = [
        "First document",
        "Second document",
        "Third document"
    ]

    embeddings = embedding.get_embeddings(texts)

    assert len(embeddings) == 3
    assert all(isinstance(emb, list) for emb in embeddings)
    assert all(len(emb) > 0 for emb in embeddings)
```

---

## Best Practices

### 1. Test Organization

```
tests/integration/
├── __init__.py
├── conftest.py                 # Shared fixtures
├── test_llm.py                 # LLM integration tests
├── test_embedding.py           # Embedding integration tests
├── test_vector_db.py           # Vector DB integration tests
├── test_x2text.py              # Text extraction tests
├── llm_test_config.py          # LLM provider configurations
├── embedding_test_config.py    # Embedding provider configurations
├── test_helpers.py             # Shared test utilities
├── .env.test.sample            # Environment template
└── README.md                   # Test documentation
```

### 2. Naming Conventions

- **Test Files**: `test_<component>.py`
- **Test Classes**: `Test<Component><Feature>`
- **Test Methods**: `test_<specific_behavior>`
- **Config Files**: `<component>_test_config.py`

### 3. Test Independence

- Each test should be independent
- No shared state between tests
- Clean up resources after tests
- Use fixtures for common setup

### 4. Assertion Patterns

```python
# ✅ Good: Specific assertions
assert result is not None
assert isinstance(result, str)
assert len(result) > 0
assert "expected" in result

# ❌ Bad: Vague assertions
assert result  # What exactly is being tested?
```

### 5. Error Message Quality

```python
# ✅ Good: Descriptive error messages
pytest.fail(f"{provider_name} failed to connect: {str(e)}")

# ❌ Bad: Generic messages
assert False, "Test failed"
```

### 6. Documentation

- Document test purpose in docstrings
- Explain non-obvious assertions
- Reference issue numbers for bug tests
- Document expected behaviors

---

## Adapter ID Reference

### Quick Reference Table

| Component | Provider | Adapter ID |
|-----------|----------|------------|
| LLM | OpenAI | `openai\|502ecf49-e47c-445c-9907-6d4b90c5cd17` |
| LLM | Anthropic | `anthropic\|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203` |
| LLM | Azure OpenAI | `azureopenai\|dd8a2e37-8319-4d9f-8a8f-be41f07b3f99` |
| LLM | AWS Bedrock | `bedrock\|8d18571f-5e96-4505-bd28-ad0379c64064` |
| LLM | Vertex AI | `vertexai\|ba80fc7b-ad08-4b36-ab0f-b92e0b3915b4` |
| LLM | Ollama | `ollama\|f88c2c3d-f6e0-455f-aa32-3f4ca4a65c2b` |
| LLM | Mistral | `mistral\|7fa87c83-fb88-4504-8711-4d7fd9b5b45f` |
| LLM | Anyscale | `anyscale\|2dbfa1f9-1b9f-41b3-a4ed-7d6e6d14a28c` |
| Embedding | OpenAI | `openai\|717a0b0e-3bbc-41dc-9f0c-5689437a1151` |
| Embedding | Azure OpenAI | `azureopenai\|9770f3f6-f8ba-4fa0-bb3a-bef48a00e66f` |
| Embedding | AWS Bedrock | `bedrock\|88199741-8d7e-4e8c-9d92-d76b0dc20c91` |
| Embedding | Vertex AI | `vertexai\|457a256b-e74f-4251-98a0-8864aafb42a5` |
| Embedding | Ollama | `ollama\|d58d7080-55a9-4542-becd-8433528e127b` |

---

## Resources

### Documentation Links

- **LiteLLM Docs**: https://docs.litellm.ai/
- **LlamaIndex Docs**: https://docs.llamaindex.ai/
- **Pytest Docs**: https://docs.pytest.org/

### Internal References

- Existing tests: `tests/integration/test_llm.py`, `test_embedding.py`
- Test configs: `llm_test_config.py`, `embedding_test_config.py`
- Environment template: `.env.test.sample`

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-10-23 | Initial documentation for test development |

---

**Document Maintained By**: Unstract QA Team
**Last Updated**: October 23, 2025
