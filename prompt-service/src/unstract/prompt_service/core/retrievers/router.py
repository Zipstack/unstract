import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class RouterRetriever(BaseRetriever):
    """Router retrieval class that routes queries to different retrieval strategies
    based on the query type and content.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using router-based retrieval technique.

        This technique analyzes the query and routes it to the most appropriate
        retrieval strategy.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(f"Retrieving chunks for {self.doc_id} using RouterRetriever.")

            if not self.llm:
                # Fallback to simple retrieval if no LLM
                logger.warning(
                    "LLM is required for RouterRetriever, falling back to simple retrieval"
                )
                return self._simple_retrieval()

            # Analyze query to determine best retrieval strategy
            strategy = self._determine_retrieval_strategy(self.prompt)

            # Route to appropriate retrieval method
            if strategy == "semantic":
                return self._semantic_retrieval()
            elif strategy == "keyword":
                return self._keyword_retrieval()
            elif strategy == "hybrid":
                return self._hybrid_retrieval()
            else:
                return self._simple_retrieval()

        except Exception as e:
            logger.error(f"Error during router retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e

    def _determine_retrieval_strategy(self, query: str) -> str:
        """Determine the best retrieval strategy for the given query.

        Args:
            query: The user query

        Returns:
            The retrieval strategy to use
        """
        try:
            prompt = f"""Analyze this query and determine the best retrieval strategy:

Query: {query}

Choose ONE of these strategies:
- "semantic": For conceptual questions requiring understanding of meaning
- "keyword": For finding specific terms, names, codes, or exact matches
- "hybrid": For queries that need both semantic understanding and specific terms

Respond with only the strategy name, nothing else."""

            response = self.llm.complete(prompt)
            if response and response.text:
                strategy = response.text.strip().lower()
                if strategy in ["semantic", "keyword", "hybrid"]:
                    logger.info(f"Selected retrieval strategy: {strategy}")
                    return strategy
        except Exception as e:
            logger.warning(f"Failed to determine retrieval strategy: {e}")

        # Default to hybrid
        return "hybrid"

    def _semantic_retrieval(self) -> set[str]:
        """Perform semantic similarity-based retrieval."""
        logger.info("Performing semantic retrieval")

        vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()
        retriever = vector_store_index.as_retriever(
            similarity_top_k=self.top_k,
            filters=MetadataFilters(
                filters=[
                    ExactMatchFilter(key="doc_id", value=self.doc_id),
                ],
            ),
        )

        nodes = retriever.retrieve(self.prompt)
        chunks: set[str] = set()

        for node in nodes:
            if node.score > 0:
                chunks.add(node.get_content())

        return chunks

    def _keyword_retrieval(self) -> set[str]:
        """Perform keyword-based retrieval."""
        logger.info("Performing keyword retrieval")

        # Extract keywords from query
        keywords = self._extract_keywords(self.prompt)

        # Retrieve using each keyword and combine results
        all_results: dict[str, float] = {}
        vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

        for keyword in keywords:
            retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k // len(keywords) if keywords else self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            nodes = retriever.retrieve(keyword)
            for node in nodes:
                if node.score > 0:
                    if node.node_id in all_results:
                        all_results[node.node_id] = max(
                            all_results[node.node_id], node.score
                        )
                    else:
                        all_results[node.node_id] = node.score

        # Get nodes again to retrieve content
        retriever = vector_store_index.as_retriever(
            similarity_top_k=self.top_k * 2,
            filters=MetadataFilters(
                filters=[
                    ExactMatchFilter(key="doc_id", value=self.doc_id),
                ],
            ),
        )

        all_nodes = retriever.retrieve(self.prompt)
        chunks: set[str] = set()

        # Sort by score and get top_k
        sorted_ids = sorted(all_results.items(), key=lambda x: x[1], reverse=True)[
            : self.top_k
        ]
        selected_ids = {node_id for node_id, _ in sorted_ids}

        for node in all_nodes:
            if node.node_id in selected_ids:
                chunks.add(node.get_content())

        return chunks

    def _hybrid_retrieval(self) -> set[str]:
        """Perform hybrid retrieval combining semantic and keyword approaches."""
        logger.info("Performing hybrid retrieval")

        # Get results from both methods
        semantic_chunks = self._semantic_retrieval()
        keyword_chunks = self._keyword_retrieval()

        # Combine results, prioritizing overlapping chunks
        all_chunks = semantic_chunks.union(keyword_chunks)

        # If we have too many chunks, prioritize those that appear in both
        if len(all_chunks) > self.top_k:
            overlap = semantic_chunks.intersection(keyword_chunks)
            remaining = all_chunks - overlap

            # Take all overlapping chunks and fill rest from remaining
            chunks = overlap
            for chunk in list(remaining)[: self.top_k - len(overlap)]:
                chunks.add(chunk)

            return chunks

        return all_chunks

    def _simple_retrieval(self) -> set[str]:
        """Fallback to simple retrieval."""
        vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()
        retriever = vector_store_index.as_retriever(
            similarity_top_k=self.top_k,
            filters=MetadataFilters(
                filters=[
                    ExactMatchFilter(key="doc_id", value=self.doc_id),
                ],
            ),
        )

        nodes = retriever.retrieve(self.prompt)
        chunks: set[str] = set()

        for node in nodes:
            if node.score > 0:
                chunks.add(node.get_content())

        return chunks

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract keywords from the query."""
        if self.llm:
            try:
                prompt = f"""Extract important keywords from this query for search purposes:

Query: {query}

Provide only the keywords, one per line, without additional text."""

                response = self.llm.complete(prompt)
                if response and response.text:
                    keywords = [
                        keyword.strip()
                        for keyword in response.text.strip().split("\n")
                        if keyword.strip()
                    ]
                    return keywords[:5]
            except Exception as e:
                logger.warning(f"Failed to extract keywords with LLM: {e}")

        # Fallback to simple keyword extraction
        # Remove common words and split
        common_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "is",
            "are",
            "was",
            "were",
        }
        words = query.lower().split()
        keywords = [word for word in words if word not in common_words and len(word) > 2]
        return keywords[:5]
