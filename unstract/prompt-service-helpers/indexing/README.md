# Extraction Module - Prompt Service Helpers

This module provides celery tasks and utilities for the document extraction pipeline, focusing on text chunking and embedding generation as part of the agentic data extraction process.

## Overview

The extraction module handles the critical step of preparing extracted text for vector database storage and retrieval. It takes raw text extracted from documents (PDFs, etc.) and processes it into searchable chunks with embeddings.

## Components

### 1. **chunking_embedding_task.py**
Main celery task that processes text for chunking and embedding generation.

**Key Features:**
- Retrieves extracted text from MinIO using SDK's FileStorage
- Generates unique document IDs using adapter configurations
- Chunks text based on user-defined parameters (chunk_size, chunk_overlap)
- Creates embeddings using configured embedding models
- Stores chunks and embeddings in vector database
- Supports document reindexing
- Calculates token usage for the entire document

**Task Name:** `chunking_embedding_task`

**Inputs:**
- `minio_text_path`: Path to extracted text in MinIO
- `chunking_params`: User-defined chunking configuration
  - `chunk_size`: Size of text chunks (default: 1000)
  - `chunk_overlap`: Overlap between chunks (default: 200)
  - `enable_smart_chunking`: Auto-adjust based on LLM context (optional)
- `embedding_params`: Embedding configuration
  - `adapter_instance_id`: Embedding model adapter ID
  - `vector_db_instance_id`: Vector database adapter ID
  - `platform_key`: Authentication key
- `llm_config`: Optional LLM configuration for smart chunking

**Outputs:**
- `doc_id`: Unique document identifier for retrieval
- `chunk_count`: Number of chunks created
- `embedding_count`: Number of embeddings generated
- `total_input_tokens`: Total tokens in the input file
- `metadata`: Processing details and statistics

### 2. **token_helper.py**
Utility for token calculation and model context window management.

**Key Features:**
- Fetches model pricing and context data from LiteLLM's public repository
- Caches model data locally with configurable TTL (default: 7 days)
- Counts tokens using tiktoken (with fallback approximation)
- Determines optimal chunk sizes based on model context windows
- Supports all major LLM providers (OpenAI, Anthropic, Meta, etc.)

**Data Source:**
```
https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
```

**Main Methods:**
- `count_tokens(text, model_name)`: Count tokens in text
- `get_model_context_window(model_name)`: Get model's max context size
- `calculate_optimal_chunk_size(model_name)`: Calculate recommended chunk size

## Usage Example

```python
from celery import Celery
from indexing.chunking_embedding_task import process_chunking_and_embedding

# Trigger the celery task
result = process_chunking_and_embedding.delay(
    minio_text_path="bucket/documents/extracted_text.txt",
    chunking_params={
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "enable_smart_chunking": True
    },
    embedding_params={
        "adapter_instance_id": "embedding-adapter-123",
        "vector_db_instance_id": "vectordb-adapter-456",
        "platform_key": "your-platform-key"
    },
    llm_config={
        "model_name": "gpt-4",
        "provider": "openai"
    }
)

# Get task result
output = result.get()
print(f"Document ID: {output['doc_id']}")
print(f"Total tokens: {output['total_input_tokens']}")
print(f"Chunks created: {output['chunk_count']}")
```

## Integration with Celery Chain

This task is designed to be part of the larger extraction pipeline:

```
Text Extraction → Chunking & Embedding → Digraph Generation → Agent Execution
```

The output `doc_id` from this task can be used by downstream agents to retrieve relevant context using RAG (Retrieval-Augmented Generation).

## Environment Variables

Required environment variables for MinIO access:
- `MINIO_ENDPOINT`: MinIO server endpoint
- `MINIO_ACCESS_KEY`: Access key for MinIO
- `MINIO_SECRET_KEY`: Secret key for MinIO
- `MINIO_BUCKET_NAME`: Default bucket name
- `MINIO_SECURE`: Use HTTPS (true/false)

## SDK Dependencies

This module heavily utilizes the Unstract SDK:
- `FileStorage`: For MinIO file operations
- `ToolAdapter`: For adapter configuration retrieval
- `ToolUtils`: For hashing and utility functions
- `VectorDB`: For vector database operations
- `Embedding`: For embedding generation

## Design Decisions

1. **No Redundant Storage**: Chunk metadata is not stored separately as it's already handled by the backend vector database.

2. **SDK-First Approach**: All operations use SDK methods to ensure consistency with the rest of the platform.

3. **Index Key Generation**: Uses the same logic as `index_v2.py` to generate unique document IDs based on file hash and configuration.

4. **Token Awareness**: Calculates and tracks token usage for cost estimation and optimization.

5. **Smart Chunking**: Optional feature that adjusts chunk size based on the LLM's context window to optimize retrieval and processing.

## Performance Considerations

- Model data is cached locally to avoid repeated API calls
- Documents are checked for existing indexing to avoid redundant processing
- Chunking and embedding happen in a single pass for efficiency
- Vector database operations are batched by the SDK

## Future Enhancements

- Support for different chunking strategies (semantic, paragraph-based)
- Parallel processing of large documents
- Support for incremental updates to existing documents
- Integration with document structure detection for smarter chunking