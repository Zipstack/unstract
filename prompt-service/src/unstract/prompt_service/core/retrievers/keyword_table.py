import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.indices.keyword_table import KeywordTableIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class KeywordTableRetriever(BaseRetriever):
    """Keyword table retrieval using LlamaIndex's native KeywordTableIndex."""

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's native KeywordTableIndex.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using LlamaIndex KeywordTableIndex."
            )

            # Get documents from vector index for keyword indexing
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Get all nodes for the document
            all_retriever = vector_store_index.as_retriever(
                similarity_top_k=1000,  # Get all nodes
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Retrieve all nodes to build keyword index
            all_nodes = all_retriever.retrieve("")

            if not all_nodes:
                logger.warning(f"No nodes found for doc_id: {self.doc_id}")
                return set()

            # Create KeywordTableIndex from nodes
            keyword_index = KeywordTableIndex(
                nodes=[node.node for node in all_nodes],
                show_progress=False,
            )

            # Create retriever from keyword index
            keyword_retriever = keyword_index.as_retriever(
                similarity_top_k=self.top_k,
            )

            # Retrieve nodes using keyword matching
            nodes = keyword_retriever.retrieve(self.prompt)

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
                f"Successfully retrieved {len(chunks)} chunks using KeywordTableIndex."
            )
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during keyword retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during keyword retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
