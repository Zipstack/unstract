"""
Celery task for chunking and embedding text extraction results.
This task handles text chunking based on user-defined parameters and generates
embeddings for vector database storage, following the pattern from index_v2.py.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from celery import shared_task
from llama_index.core import Document
from llama_index.core.vector_stores import (
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
    VectorStoreQuery,
    VectorStoreQueryResult,
)
from unstract.sdk.adapter import ToolAdapter
from unstract.sdk.embedding import Embedding
from unstract.sdk.exceptions import IndexingError, SdkError
from unstract.sdk.file_storage.impl import FileStorage
from unstract.sdk.file_storage.provider import FileStorageProvider
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.utils.tool_utils import ToolUtils
from unstract.sdk.vector_db import VectorDB

from .token_helper import TokenCalculationHelper

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="chunking_embedding_task")
def process_chunking_and_embedding(
    self,
    minio_text_path: str,
    chunking_params: Dict[str, Any],
    embedding_params: Dict[str, Any],
    llm_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process text chunking and embedding generation following index_v2 pattern.

    Args:
        minio_text_path: Path to the extracted text file in MinIO
        chunking_params: Parameters for chunking including:
            - chunk_size: Target chunk size in tokens/characters
            - chunk_overlap: Overlap between chunks
            - enable_smart_chunking: Enable intelligent chunking based on LLM context (optional)
        embedding_params: Parameters for embedding including:
            - adapter_instance_id: ID of the embedding adapter
            - vector_db_instance_id: ID of the vector database adapter
            - platform_key: Platform key for authentication
            - x2text_instance_id: ID of the x2text adapter (optional)
            - file_hash: Hash of the file (optional, will be calculated if not provided)
        llm_config: Optional LLM configuration for context size determination

    Returns:
        Dict containing:
            - doc_id: Document ID for accessing chunks and embeddings
            - minio_text_path: Original text file path
            - chunk_count: Number of chunks created
            - embedding_count: Number of embeddings generated
            - total_input_tokens: Total tokens in the input file
            - metadata: Additional processing metadata
    """

    task_id = self.request.id
    logger.info(f"[Task {task_id}] Starting chunking and embedding task")

    try:
        # Step 1: Initialize FileStorage for MinIO access using SDK
        file_storage = FileStorage(
            provider=FileStorageProvider.MINIO,
            **get_minio_config()
        )

        # Step 2: Retrieve the extracted text from MinIO using SDK read method
        logger.info(f"[Task {task_id}] Retrieving text from MinIO: {minio_text_path}")
        text_content = file_storage.read(
            path=minio_text_path,
            mode="r",
            encoding="utf-8"
        )

        if not text_content:
            raise ValueError(f"No text content found at {minio_text_path}")

        # Step 3: Initialize token calculation helper
        token_helper = TokenCalculationHelper()

        # Calculate total input tokens in the file
        model_name = llm_config.get("model_name", "gpt-3.5-turbo") if llm_config else "gpt-3.5-turbo"
        total_input_tokens = token_helper.count_tokens(text_content, model_name)
        logger.info(f"[Task {task_id}] Total input tokens in file: {total_input_tokens}")

        # Step 4: Get chunking parameters from user input
        chunk_size = chunking_params.get("chunk_size", 1000)
        chunk_overlap = chunking_params.get("chunk_overlap", 200)
        enable_smart_chunking = chunking_params.get("enable_smart_chunking", False)

        # Optional: Adjust chunk size based on LLM context if smart chunking is enabled
        if enable_smart_chunking and llm_config:
            provider = llm_config.get("provider")
            optimal_chunk_size = token_helper.calculate_optimal_chunk_size(
                model_name, provider, target_utilization=0.25
            )
            if optimal_chunk_size:
                chunk_size = min(chunk_size, optimal_chunk_size)
                logger.info(
                    f"[Task {task_id}] Adjusted chunk size to {chunk_size} "
                    f"based on model {model_name} context window"
                )

        # Step 5: Initialize SDK components
        platform_key = embedding_params.get("platform_key", "")
        tool = BaseTool(platform_key=platform_key)

        # Step 6: Generate document ID using SDK methods (similar to index key in index_v2)
        doc_id = generate_index_key_with_sdk(
            tool=tool,
            file_hash=embedding_params.get("file_hash"),
            file_path=minio_text_path,
            embedding_instance_id=embedding_params.get("adapter_instance_id"),
            vector_db_instance_id=embedding_params.get("vector_db_instance_id"),
            x2text_instance_id=embedding_params.get("x2text_instance_id"),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            file_storage=file_storage,
        )

        logger.info(f"[Task {task_id}] Generated doc_id: {doc_id}")

        # Step 7: Initialize embedding using SDK
        embedding = Embedding(
            tool=tool,
            adapter_instance_id=embedding_params.get("adapter_instance_id"),
        )

        # Step 8: Initialize vector DB using SDK
        vector_db = VectorDB(
            tool=tool,
            adapter_instance_id=embedding_params.get("vector_db_instance_id"),
            embedding=embedding,
        )

        # Step 9: Check if document is already indexed using SDK methods
        doc_already_indexed = is_document_indexed(doc_id, embedding, vector_db, tool)

        reindex = embedding_params.get("reindex", False)
        if doc_already_indexed and not reindex:
            logger.info(f"[Task {task_id}] Document already indexed with doc_id: {doc_id}")
            return {
                "doc_id": doc_id,
                "minio_text_path": minio_text_path,
                "chunk_count": 0,
                "embedding_count": 0,
                "total_input_tokens": total_input_tokens,
                "metadata": {
                    "already_indexed": True,
                    "task_id": task_id,
                }
            }

        # Step 10: Prepare document for chunking (following index_v2 pattern)
        logger.info(f"[Task {task_id}] Preparing document for chunking")

        # Create document structure similar to index_v2
        full_text = [
            {
                "section": "full",
                "text_contents": str(text_content),
            }
        ]

        # Convert to LlamaIndex Document using SDK patterns
        documents = prepare_documents_with_sdk(doc_id, full_text, tool)

        # Step 11: Delete existing nodes if reindexing using SDK methods
        if reindex and doc_already_indexed:
            logger.info(f"[Task {task_id}] Deleting existing nodes for reindexing")
            try:
                vector_db.delete(ref_doc_id=doc_id)
                tool.stream_log(f"Deleted existing nodes for {doc_id}")
            except Exception as e:
                logger.error(f"[Task {task_id}] Error deleting nodes: {e}")
                raise SdkError(f"Error deleting nodes for {doc_id}: {e}") from e

        # Step 12: Perform indexing with chunking using SDK methods
        logger.info(
            f"[Task {task_id}] Indexing with chunk_size: {chunk_size}, "
            f"chunk_overlap: {chunk_overlap}"
        )

        try:
            # Using SDK's vector_db.index_document method (follows index_v2._trigger_indexing)
            tool.stream_log("Adding nodes to vector db...")

            # The SDK's index_document method handles chunking internally
            nodes = vector_db.index_document(
                documents,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                show_progress=True,
            )

            tool.stream_log(f"File has been indexed successfully")
            logger.info(f"[Task {task_id}] Successfully indexed {len(nodes) if nodes else 0} nodes")

            # Count the nodes created
            chunk_count = len(nodes) if nodes else 0

        except Exception as e:
            tool.stream_log(
                f"Error adding nodes to vector db: {e}",
                level="ERROR",
            )
            raise IndexingError(str(e)) from e

        # Step 13: Count embeddings (one per chunk)
        embedding_count = chunk_count  # Assuming one embedding per chunk

        # Calculate average chunk size in tokens
        avg_chunk_tokens = total_input_tokens // chunk_count if chunk_count > 0 else 0

        # Prepare response
        result = {
            "doc_id": doc_id,
            "minio_text_path": minio_text_path,
            "chunk_count": chunk_count,
            "embedding_count": embedding_count,
            "total_input_tokens": total_input_tokens,
            "metadata": {
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "average_chunk_tokens": avg_chunk_tokens,
                "text_length": len(text_content),
                "model_name": model_name,
                "task_id": task_id,
                "reindexed": reindex and doc_already_indexed,
            }
        }

        logger.info(f"[Task {task_id}] Chunking and embedding completed successfully")
        return result

    except Exception as e:
        logger.error(f"[Task {task_id}] Error in chunking and embedding: {str(e)}")
        raise


def generate_index_key_with_sdk(
    tool: BaseTool,
    file_hash: Optional[str],
    file_path: str,
    embedding_instance_id: str,
    vector_db_instance_id: str,
    x2text_instance_id: Optional[str],
    chunk_size: int,
    chunk_overlap: int,
    file_storage: FileStorage,
) -> str:
    """
    Generate a unique index key using SDK methods.
    This follows the pattern from index_v2.generate_index_key but uses SDK methods.

    Args:
        tool: BaseTool instance for SDK operations
        file_hash: Optional pre-computed file hash
        file_path: Path to the file
        embedding_instance_id: Embedding adapter instance ID
        vector_db_instance_id: Vector DB adapter instance ID
        x2text_instance_id: Optional x2text adapter instance ID
        chunk_size: Chunk size for splitting
        chunk_overlap: Chunk overlap for splitting
        file_storage: FileStorage instance for hash calculation

    Returns:
        Unique index key (doc_id) for the document
    """
    if not file_hash:
        # Use SDK's file storage method to calculate file hash
        file_hash = file_storage.get_hash_from_file(path=file_path)

    # Use SDK's ToolAdapter to get adapter configurations
    # This ensures we're using the same configuration as index_v2
    index_key = {
        "file_hash": file_hash,
        "chunk_size": str(chunk_size),  # Convert to string for compatibility
        "chunk_overlap": str(chunk_overlap),  # Convert to string for compatibility
    }

    # Get adapter configurations using SDK methods (if tool has platform connection)
    try:
        # Get vector DB config using SDK
        vector_db_config = ToolAdapter.get_adapter_config(
            tool, vector_db_instance_id
        )
        if vector_db_config:
            index_key["vector_db_config"] = vector_db_config

        # Get embedding config using SDK
        embedding_config = ToolAdapter.get_adapter_config(
            tool, embedding_instance_id
        )
        if embedding_config:
            index_key["embedding_config"] = embedding_config

        # Get x2text config if provided
        if x2text_instance_id:
            x2text_config = ToolAdapter.get_adapter_config(
                tool, x2text_instance_id
            )
            if x2text_config:
                index_key["x2text_config"] = x2text_config

    except Exception as e:
        logger.warning(
            f"Could not retrieve adapter configs, using instance IDs instead: {e}"
        )
        # Fallback to using instance IDs directly
        index_key["vector_db_instance_id"] = vector_db_instance_id
        index_key["embedding_instance_id"] = embedding_instance_id
        if x2text_instance_id:
            index_key["x2text_instance_id"] = x2text_instance_id

    # Use SDK's ToolUtils.hash_str to generate the hash
    # Sort keys to ensure consistent hashing
    hashed_index_key = ToolUtils.hash_str(
        json.dumps(index_key, sort_keys=True),
        hash_method="sha256"  # Use SHA256 for better uniqueness
    )

    return hashed_index_key


def is_document_indexed(
    doc_id: str,
    embedding: Embedding,
    vector_db: VectorDB,
    tool: BaseTool,
) -> bool:
    """
    Check if a document is already indexed using SDK methods.
    This follows the pattern from index_v2.is_document_indexed.

    Args:
        doc_id: Document ID to check
        embedding: Embedding instance
        vector_db: Vector DB instance
        tool: BaseTool instance for logging

    Returns:
        True if document is already indexed, False otherwise
    """
    try:
        # Create filter for doc_id using SDK patterns
        doc_id_eq_filter = MetadataFilter.from_dict(
            {"key": "doc_id", "operator": FilterOperator.EQ, "value": doc_id}
        )
        filters = MetadataFilters(filters=[doc_id_eq_filter])

        # Query with minimal embedding using SDK method
        q = VectorStoreQuery(
            query_embedding=embedding.get_query_embedding(" "),
            doc_ids=[doc_id],
            filters=filters,
        )

        # Check if nodes exist using SDK's vector_db.query
        result: VectorStoreQueryResult = vector_db.query(query=q)

        if len(result.nodes) > 0:
            tool.stream_log(f"Found {len(result.nodes)} nodes for {doc_id}")
            return True
        else:
            tool.stream_log(f"No nodes found for {doc_id}")
            return False

    except Exception as e:
        logger.warning(
            f"Error querying vector DB: {str(e)}, proceeding to index",
            exc_info=True,
        )
        return False


def prepare_documents_with_sdk(
    doc_id: str,
    full_text: List[Dict[str, Any]],
    tool: BaseTool
) -> List[Document]:
    """
    Prepare documents for indexing using SDK patterns.
    This follows the pattern from index_v2._prepare_documents.

    Args:
        doc_id: Document identifier
        full_text: List of text sections with metadata
        tool: BaseTool instance for logging

    Returns:
        List of LlamaIndex Document objects
    """
    documents = []

    try:
        for item in full_text:
            text = item["text_contents"]

            # Create Document using LlamaIndex (as used by SDK)
            document = Document(
                text=text,
                doc_id=doc_id,
                metadata={"section": item["section"]},
            )
            document.id_ = doc_id
            documents.append(document)

        tool.stream_log(f"Number of documents: {len(documents)}")
        return documents

    except Exception as e:
        tool.stream_log(
            f"Error while processing documents {doc_id}: {e}",
            level="ERROR",
        )
        raise SdkError(
            f"Error while processing documents for indexing {doc_id}: {e}"
        ) from e


def get_minio_config() -> Dict[str, Any]:
    """
    Get MinIO configuration from environment or settings.
    This uses SDK-compatible configuration format.

    Returns:
        Dict with MinIO configuration parameters for SDK FileStorage
    """
    import os

    # Return configuration in the format expected by SDK's FileStorage
    return {
        "endpoint": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        "access_key": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        "secret_key": os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        "secure": os.getenv("MINIO_SECURE", "false").lower() == "true",
        "bucket_name": os.getenv("MINIO_BUCKET_NAME", "unstract-data"),
    }