import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class RecursiveRetrieval(BaseRetriever):
    """Recursive retrieval class that retrieves nodes and explores related content
    to provide more comprehensive context.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using recursive retrieval technique.

        This technique retrieves initial nodes and then explores related nodes
        based on similarity to build more comprehensive context.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(f"Retrieving chunks for {self.doc_id} using RecursiveRetrieval.")

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Create base retriever with metadata filters
            base_retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Initial retrieval
            initial_nodes = base_retriever.retrieve(self.prompt)

            # Track all retrieved content with scores
            all_content: dict[str, float] = {}
            processed_queries: set[str] = {self.prompt}

            # Add initial nodes
            for node in initial_nodes:
                if node.score > 0:
                    all_content[node.node_id] = (node.get_content(), node.score)

            # Perform recursive retrieval
            if len(initial_nodes) > 0 and self.llm:
                # Extract key concepts from initial results
                key_concepts = self._extract_key_concepts(
                    [node.get_content() for node in initial_nodes[:3]]
                )

                # Retrieve additional content based on key concepts
                for concept in key_concepts:
                    if concept not in processed_queries:
                        processed_queries.add(concept)

                        # Retrieve nodes for this concept
                        concept_nodes = base_retriever.retrieve(concept)

                        # Add new nodes with adjusted scores
                        for node in concept_nodes[: self.top_k // 2]:
                            if node.score > 0 and node.node_id not in all_content:
                                # Reduce score for indirect matches
                                all_content[node.node_id] = (
                                    node.get_content(),
                                    node.score * 0.7,
                                )

            # Sort by score and get top_k results
            sorted_content = sorted(
                all_content.items(), key=lambda x: x[1][1], reverse=True
            )[: self.top_k]

            # Extract unique text chunks
            chunks: set[str] = {content for _, (content, _) in sorted_content}

            logger.info(
                f"Successfully retrieved {len(chunks)} chunks using recursive retrieval."
            )
            return chunks

        except Exception as e:
            logger.error(f"Error during recursive retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e

    def _extract_key_concepts(self, initial_results: list[str]) -> list[str]:
        """Extract key concepts from initial retrieval results.

        Args:
            initial_results: List of initial text chunks

        Returns:
            List of key concepts to search for
        """
        if not self.llm or not initial_results:
            return []

        try:
            # Combine initial results
            context = "\n\n".join(initial_results[:3])

            prompt = f"""Based on the following text, extract 3-5 key concepts or topics that would help find related information:

{context}

Provide only the key concepts, one per line, without numbering or additional text."""

            response = self.llm.complete(prompt)
            if response and response.text:
                concepts = [
                    concept.strip()
                    for concept in response.text.strip().split("\n")
                    if concept.strip()
                ]
                return concepts[:5]
        except Exception as e:
            logger.warning(f"Failed to extract key concepts: {e}")

        return []
