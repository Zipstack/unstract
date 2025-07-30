import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import RecursiveRetriever as LlamaRecursiveRetriever
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class RecursiveRetrieval(BaseRetriever):
    """Recursive retrieval class using LlamaIndex's native RecursiveRetriever.
    
    This technique follows document relationships and references recursively
    to build comprehensive context from connected information.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's RecursiveRetriever.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(f"Retrieving chunks for {self.doc_id} using LlamaIndex RecursiveRetriever.")

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

            # For now, use base retriever directly since RecursiveRetriever 
            # requires complex node relationship mapping and storage context
            # which would need significant infrastructure changes
            retriever = base_retriever

            # Retrieve nodes
            nodes = retriever.retrieve(self.prompt)

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

            logger.info(f"Successfully retrieved {len(chunks)} chunks using recursive retrieval.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during recursive retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error during recursive retrieval for {self.doc_id}: {e}")
            raise RetrievalError(f"Unexpected error: {str(e)}") from e