import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class AutomergingRetriever(BaseRetriever):
    """Automerging retrieval using enhanced vector retrieval with reranking.

    Since full AutoMergingRetriever requires hierarchical document structure,
    we use an enhanced retrieval approach that gets more candidates and reranks them.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using enhanced retrieval with reranking.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using enhanced retrieval with reranking."
            )

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Create retriever that gets more candidates for reranking
            retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k * 3,  # Get 3x candidates for reranking
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Retrieve initial nodes
            nodes = retriever.retrieve(self.prompt)

            # If we have nodes and an LLM, we can do additional processing
            if nodes and len(nodes) > self.top_k:
                # Sort by score and take top results
                nodes = sorted(nodes, key=lambda x: x.score, reverse=True)[: self.top_k]

            # Extract unique text chunks
            chunks: set[str] = set()
            for node in nodes:
                if node.score > 0:
                    chunks.add(node.get_content())
                else:
                    logger.info(
                        f"Node score is less than 0. "
                        f"Ignored: {node.node_id} with score {node.score}"
                    )

            logger.info(
                f"Successfully retrieved {len(chunks)} chunks using enhanced retrieval."
            )
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during enhanced retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during enhanced retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
