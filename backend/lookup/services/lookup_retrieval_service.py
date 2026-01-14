"""RAG retrieval service for Lookup projects using similarity search with ranking.

This module provides functionality to retrieve relevant context chunks from
indexed reference data using vector similarity search. Chunks are ranked by
similarity score and annotated with source information for better context.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import PromptIdeBaseTool
from utils.user_context import UserContext

from lookup.models import LookupIndexManager

if TYPE_CHECKING:
    from lookup.models import LookupProfileManager

from unstract.sdk1.constants import LogLevel
from unstract.sdk1.embedding import EmbeddingCompat
from unstract.sdk1.vector_db import VectorDB

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved chunk with metadata for ranking and attribution."""

    content: str
    score: float
    source_file: str
    doc_id: str


class LookupRetrievalService:
    """Service to perform RAG retrieval for Lookup projects.

    Uses simple cosine similarity search against indexed reference data.
    When chunk_size > 0, this service retrieves relevant chunks instead
    of loading the entire reference data.
    """

    def __init__(self, profile: "LookupProfileManager", org_id: str | None = None):
        """Initialize the retrieval service.

        Args:
            profile: LookupProfileManager with adapter configuration
            org_id: Organization ID (if None, gets from UserContext)
        """
        self.profile = profile
        self.org_id = org_id or UserContext.get_organization_identifier()
        logger.info(
            f"LookupRetrievalService initialized with org_id='{self.org_id}' "
            f"(provided={org_id}, from_context={UserContext.get_organization_identifier()})"
        )

    def retrieve_context(
        self, query: str, project_id: str, min_score: float = 0.3
    ) -> str:
        r"""Retrieve relevant context chunks from indexed data sources.

        Queries the vector DB for chunks semantically similar to the query,
        filtering by doc_id to ensure results come from the correct
        indexed reference data. Chunks are ranked by similarity score and
        annotated with source file information.

        Args:
            query: The semantic query to search for (built from input_data)
            project_id: UUID of the lookup project
            min_score: Minimum similarity score threshold (default 0.3)

        Returns:
            Concatenated retrieved chunks as context string, sorted by
            relevance score (highest first) with source attribution.
            Returns empty string if no indexed sources found.

        Example:
            >>> service = LookupRetrievalService(profile)
            >>> context = service.retrieve_context("vendor: Slack, type: SaaS", project_id)
            >>> print(context[:100])
            '=== Source: vendors.csv (relevance: 0.89) ===\nSlack Technologies Inc...'
        """
        # Get all indexed data sources for this project with extraction complete
        index_managers = LookupIndexManager.objects.filter(
            data_source__project_id=project_id,
            data_source__is_latest=True,
            data_source__extraction_status="completed",  # Only fully extracted sources
            profile_manager=self.profile,
            raw_index_id__isnull=False,
        ).select_related("data_source")

        if not index_managers.exists():
            logger.warning(
                f"No indexed data sources for project {project_id}. "
                "Ensure data sources are uploaded and extraction is complete."
            )
            return ""

        # Build doc_id to source file mapping for attribution
        doc_id_to_source: dict[str, str] = {}
        for im in index_managers:
            if im.raw_index_id:
                doc_id_to_source[im.raw_index_id] = im.data_source.file_name

        doc_ids = list(doc_id_to_source.keys())

        if not doc_ids:
            logger.warning(f"No valid doc_ids found for project {project_id}")
            return ""

        logger.info(
            f"Retrieving context for project {project_id} "
            f"from {len(doc_ids)} indexed sources: {list(doc_id_to_source.values())}"
        )

        # Retrieve from each doc_id and aggregate results with metadata
        all_chunks: list[RetrievedChunk] = []
        for doc_id in doc_ids:
            source_file = doc_id_to_source.get(doc_id, "unknown")
            try:
                chunks = self._retrieve_chunks(query, doc_id, source_file, min_score)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(
                    f"Failed to retrieve chunks for doc_id {doc_id} "
                    f"(source: {source_file}): {e}"
                )
                # Continue with other doc_ids

        if not all_chunks:
            logger.warning(
                f"No chunks retrieved for project {project_id} with query: {query[:100]}. "
                f"This may indicate poor semantic match or indexing issues."
            )
            return ""

        # Sort by score (highest first) for better context quality
        all_chunks.sort(key=lambda c: c.score, reverse=True)

        # Deduplicate by content while preserving score-based order
        seen_content: set[str] = set()
        unique_chunks: list[RetrievedChunk] = []
        for chunk in all_chunks:
            if chunk.content not in seen_content:
                seen_content.add(chunk.content)
                unique_chunks.append(chunk)

        logger.info(
            f"Retrieved {len(unique_chunks)} unique chunks "
            f"(from {len(all_chunks)} total) for project {project_id}. "
            f"Score range: {unique_chunks[-1].score:.3f} - {unique_chunks[0].score:.3f}"
        )

        # Format chunks with source attribution for LLM context
        formatted_chunks = []
        for chunk in unique_chunks:
            header = f"=== Source: {chunk.source_file} (relevance: {chunk.score:.2f}) ==="
            formatted_chunks.append(f"{header}\n{chunk.content}")

        return "\n\n".join(formatted_chunks)

    def _retrieve_chunks(
        self, query: str, doc_id: str, source_file: str, min_score: float = 0.3
    ) -> list[RetrievedChunk]:
        """Retrieve chunks from vector DB with similarity scores.

        Uses the configured embedding model and vector store from the profile
        to perform cosine similarity search with doc_id filtering. Returns
        chunks with their similarity scores for ranking.

        Args:
            query: The semantic query to search for
            doc_id: Document ID to filter results (from LookupIndexManager)
            source_file: Source file name for attribution
            min_score: Minimum similarity score threshold (default 0.3)

        Returns:
            List of RetrievedChunk objects with content, score, and source info
        """
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=self.org_id)

        # Initialize embedding model from profile
        embedding = EmbeddingCompat(
            adapter_instance_id=str(self.profile.embedding_model.id),
            tool=util,
            kwargs={},
        )

        # Initialize vector DB from profile
        vector_db = VectorDB(
            tool=util,
            adapter_instance_id=str(self.profile.vector_store.id),
            embedding=embedding,
        )

        try:
            # Get vector store index for retrieval
            vector_store_index = vector_db.get_vector_store_index()

            # Create retriever with doc_id filter and top-k from profile
            retriever = vector_store_index.as_retriever(
                similarity_top_k=self.profile.similarity_top_k,
                filters=MetadataFilters(
                    filters=[ExactMatchFilter(key="doc_id", value=doc_id)],
                ),
            )

            # Execute retrieval
            logger.info(
                f"Executing vector retrieval for doc_id={doc_id}, "
                f"query='{query[:100]}...', top_k={self.profile.similarity_top_k}"
            )
            nodes = retriever.retrieve(query)

            logger.info(f"Vector DB returned {len(nodes)} nodes for doc_id {doc_id}")

            # Extract chunks with scores above threshold
            chunks: list[RetrievedChunk] = []
            for node in nodes:
                logger.debug(
                    f"Node {node.node_id}: score={node.score:.4f}, "
                    f"content_length={len(node.get_content())}"
                )
                if node.score >= min_score:
                    chunks.append(
                        RetrievedChunk(
                            content=node.get_content(),
                            score=node.score,
                            source_file=source_file,
                            doc_id=doc_id,
                        )
                    )
                else:
                    logger.debug(
                        f"Ignored node {node.node_id} with score {node.score:.3f} "
                        f"(below threshold {min_score})"
                    )

            if len(nodes) > 0 and len(chunks) == 0:
                logger.warning(
                    f"All {len(nodes)} nodes for doc_id {doc_id} were below "
                    f"min_score threshold ({min_score}). Highest score: "
                    f"{max(n.score for n in nodes):.4f}"
                )
            elif len(nodes) == 0:
                logger.warning(
                    f"Vector DB returned 0 nodes for doc_id {doc_id}. "
                    "This doc_id may not exist in the vector DB - check indexing."
                )

            logger.info(
                f"Retrieved {len(chunks)} chunks for doc_id {doc_id} "
                f"(source: {source_file})"
            )
            return chunks

        finally:
            # Always close vector DB connection
            vector_db.close()
