"""Indexing logic for the legacy executor.

Adapted from ``prompt-service/.../core/index_v2.py``.
Performs document chunking and vector DB indexing.

Heavy dependencies (``llama_index``, ``openai``, vectordb adapters)
are imported lazily inside methods to avoid protobuf descriptor
conflicts at test-collection time.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from executor.executors.dto import (
    ChunkingConfig,
    FileInfo,
    InstanceIdentifiers,
    ProcessingOptions,
)
from unstract.sdk1.constants import LogLevel
from unstract.sdk1.exceptions import SdkError, parse_litellm_err
from unstract.sdk1.file_storage.impl import FileStorage
from unstract.sdk1.file_storage.provider import FileStorageProvider
from unstract.sdk1.platform import PlatformHelper as ToolAdapter
from unstract.sdk1.tool.stream import StreamMixin
from unstract.sdk1.utils.tool import ToolUtils

if TYPE_CHECKING:
    from unstract.sdk1.embedding import Embedding
    from unstract.sdk1.vector_db import VectorDB

logger = logging.getLogger(__name__)


class Index:
    def __init__(
        self,
        tool: StreamMixin,
        instance_identifiers: InstanceIdentifiers,
        chunking_config: ChunkingConfig,
        processing_options: ProcessingOptions,
        run_id: str | None = None,
        capture_metrics: bool = False,
    ):
        self.tool = tool
        self._run_id = run_id
        self._capture_metrics = capture_metrics
        self.instance_identifiers = instance_identifiers
        self.chunking_config = chunking_config
        self.processing_options = processing_options
        self._metrics = {}

    def generate_index_key(
        self,
        file_info: FileInfo,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> str:
        """Generate a unique index key for document indexing."""
        if not file_info.file_path and not file_info.file_hash:
            raise ValueError("One of `file_path` or `file_hash` need to be provided")

        file_hash = file_info.file_hash
        if not file_hash:
            file_hash = fs.get_hash_from_file(path=file_info.file_path)

        index_key = {
            "file_hash": file_hash,
            "vector_db_config": ToolAdapter.get_adapter_config(
                self.tool, self.instance_identifiers.vector_db_instance_id
            ),
            "embedding_config": ToolAdapter.get_adapter_config(
                self.tool, self.instance_identifiers.embedding_instance_id
            ),
            "x2text_config": ToolAdapter.get_adapter_config(
                self.tool, self.instance_identifiers.x2text_instance_id
            ),
            "chunk_size": str(self.chunking_config.chunk_size),
            "chunk_overlap": str(self.chunking_config.chunk_overlap),
        }
        hashed_index_key = ToolUtils.hash_str(json.dumps(index_key, sort_keys=True))
        return hashed_index_key

    def is_document_indexed(
        self,
        doc_id: str,
        embedding: Embedding,
        vector_db: VectorDB,
    ) -> bool:
        """Check if nodes are already present in the vector DB for a doc_id."""
        from llama_index.core.vector_stores import (
            FilterOperator,
            MetadataFilter,
            MetadataFilters,
            VectorStoreQuery,
            VectorStoreQueryResult,
        )

        doc_id_eq_filter = MetadataFilter.from_dict(
            {"key": "doc_id", "operator": FilterOperator.EQ, "value": doc_id}
        )
        filters = MetadataFilters(filters=[doc_id_eq_filter])
        q = VectorStoreQuery(
            query_embedding=embedding.get_query_embedding(" "),
            doc_ids=[doc_id],
            filters=filters,
        )

        doc_id_found = False
        try:
            n: VectorStoreQueryResult = vector_db.query(query=q)
            if len(n.nodes) > 0:
                doc_id_found = True
                self.tool.stream_log(f"Found {len(n.nodes)} nodes for {doc_id}")
            else:
                self.tool.stream_log(f"No nodes found for {doc_id}")
        except Exception as e:
            logger.warning(
                f"Error querying {self.instance_identifiers.vector_db_instance_id}:"
                f" {str(e)}, proceeding to index",
                exc_info=True,
            )

        if doc_id_found and not self.processing_options.reindex:
            self.tool.stream_log(f"File was indexed already under {doc_id}")
            return doc_id_found

        return doc_id_found

    def perform_indexing(
        self,
        vector_db: VectorDB,
        doc_id: str,
        extracted_text: str,
        doc_id_found: bool,
    ) -> str:
        from unstract.sdk1.adapters.vectordb.no_op.src.no_op_custom_vectordb import (
            NoOpCustomVectorDB,
        )

        if isinstance(
            vector_db.get_vector_db(
                adapter_instance_id=self.instance_identifiers.vector_db_instance_id,
                embedding_dimension=1,
            ),
            (NoOpCustomVectorDB),
        ):
            return doc_id

        self.tool.stream_log("Indexing file...")
        full_text = [
            {
                "section": "full",
                "text_contents": str(extracted_text),
            }
        ]
        documents = self._prepare_documents(doc_id, full_text)
        if self.processing_options.reindex and doc_id_found:
            self.delete_nodes(vector_db, doc_id)
        self._trigger_indexing(vector_db, documents)
        return doc_id

    def _trigger_indexing(self, vector_db: Any, documents: list) -> None:
        import openai

        self.tool.stream_log("Adding nodes to vector db...")
        try:
            vector_db.index_document(
                documents,
                chunk_size=self.chunking_config.chunk_size,
                chunk_overlap=self.chunking_config.chunk_overlap,
                show_progress=True,
            )
            self.tool.stream_log("File has been indexed successfully")
        except openai.OpenAIError as e:
            e = parse_litellm_err(e)
            raise e
        except Exception as e:
            self.tool.stream_log(
                f"Error adding nodes to vector db: {e}",
                level=LogLevel.ERROR,
            )
            raise e

    def delete_nodes(self, vector_db: Any, doc_id: str) -> None:
        try:
            vector_db.delete(ref_doc_id=doc_id)
            self.tool.stream_log(f"Deleted nodes for {doc_id}")
        except Exception as e:
            self.tool.stream_log(
                f"Error deleting nodes for {doc_id}: {e}",
                level=LogLevel.ERROR,
            )
            raise SdkError(f"Error deleting nodes for {doc_id}: {e}") from e

    def _prepare_documents(self, doc_id: str, full_text: Any) -> list:
        from llama_index.core import Document

        documents = []
        try:
            for item in full_text:
                text = item["text_contents"]
                document = Document(
                    text=text,
                    doc_id=doc_id,
                    metadata={"section": item["section"]},
                )
                document.id_ = doc_id
                documents.append(document)
            self.tool.stream_log(f"Number of documents: {len(documents)}")
            return documents
        except Exception as e:
            self.tool.stream_log(
                f"Error while processing documents {doc_id}: {e}",
                level=LogLevel.ERROR,
            )
            raise SdkError(
                f"Error while processing documents for indexing {doc_id}: {e}"
            ) from e
