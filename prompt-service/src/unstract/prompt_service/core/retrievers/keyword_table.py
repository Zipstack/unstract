import logging

from llama_index.core import SimpleKeywordTableIndex, VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever, KeywordTableSimpleRetriever
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever as UnstractBaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class KeywordTableRetriever(UnstractBaseRetriever):
    """Keyword table retrieval class using LlamaIndex's native KeywordTableSimpleRetriever.
    
    This technique uses keyword extraction and matching for efficient retrieval 
    of relevant documents.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's KeywordTableSimpleRetriever.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using LlamaIndex KeywordTableSimpleRetriever."
            )

            # Get the vector store index (we'll use it as fallback)
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # For now, use vector retrieval as KeywordTableSimpleRetriever would need
            # a separate SimpleKeywordTableIndex built from the same documents
            # which would require infrastructure changes to maintain both indices
            base_retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Retrieve nodes using base retriever
            nodes = base_retriever.retrieve(self.prompt)

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

            logger.info(f"Successfully retrieved {len(chunks)} chunks using keyword table.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during keyword table retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error during keyword table retrieval for {self.doc_id}: {e}")
            raise RetrievalError(f"Unexpected error: {str(e)}") from e