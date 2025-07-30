import logging

from llama_index.core import VectorStoreIndex
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class KeywordTableRetriever(BaseRetriever):
    """Keyword table retrieval using LlamaIndex's BM25Retriever.
    
    BM25 is a ranking function that considers term frequency saturation and 
    document length for keyword-based retrieval.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's BM25Retriever.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using LlamaIndex BM25Retriever."
            )

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Get all nodes from the index for the specific doc_id
            # First, use vector retriever to get nodes for this doc_id
            vector_retriever = vector_store_index.as_retriever(
                similarity_top_k=100,  # Get more nodes to build BM25 index
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )
            
            # Retrieve all nodes for this document
            all_nodes = vector_retriever.retrieve("")  # Empty query to get all nodes
            
            if all_nodes:
                # Create BM25 retriever from the nodes
                bm25_retriever = BM25Retriever.from_defaults(
                    nodes=[node.node for node in all_nodes],
                    similarity_top_k=self.top_k,
                )
                
                # Retrieve using BM25
                nodes = bm25_retriever.retrieve(self.prompt)
            else:
                # Fallback to vector retrieval if no nodes found
                logger.warning(f"No nodes found for doc_id {self.doc_id}, falling back to vector retrieval")
                vector_retriever.similarity_top_k = self.top_k
                nodes = vector_retriever.retrieve(self.prompt)

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

            logger.info(f"Successfully retrieved {len(chunks)} chunks using BM25.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during BM25 retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error during BM25 retrieval for {self.doc_id}: {e}")
            raise RetrievalError(f"Unexpected error: {str(e)}") from e