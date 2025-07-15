import logging

from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.retrievers import QueryFusionRetriever
from llama_index.retrievers import BM25Retriever

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class FusionRetriever(BaseRetriever):
    """Fusion Retriever class that combines vector search with keyword search.
    
    This retriever uses LlamaIndex's QueryFusionRetriever to combine results from
    vector similarity search and BM25 keyword search for more robust retrieval.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using fusion of vector and keyword search.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving context for prompt: {self.prompt} with doc_id: {self.doc_id}"
            )
            
            # Get vector store index
            vector_index = self.vector_db.get_vector_store_index()
            bm25_retriever = BM25Retriever(index=vector_index, similarity_top_k=self.top_k)

            # Create vector retriever with filters for the document ID
            vector_retriever = vector_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )
            
            # Create fusion retriever that combines both methods
            fusion_retriever = QueryFusionRetriever(
                retrievers=[vector_retriever, bm25_retriever],
                similarity_top_k=self.top_k,
                use_original_query=True,  # Use the original query for all retrievers
                llm=self.llm  # Use the LLM for query rewriting if needed
            )
            
            # Retrieve nodes
            nodes = fusion_retriever.retrieve(self.prompt)
            
            # Extract content from nodes
            context = set()
            for node in nodes:
                if node.score > 0:
                    context.add(node.get_content())
                else:
                    logger.info(
                        f"Node score is less than 0. "
                        f"Ignored: {node.node_id} with score {node.score}"
                    )
            
            logger.info(f"Successfully retrieved {len(context)} chunks using Fusion Retriever.")
            return context
            
        except Exception as e:
            logger.error(f"Error during fusion retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
