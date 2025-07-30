import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class FusionRetriever(BaseRetriever):
    """Fusion retrieval class using LlamaIndex's native QueryFusionRetriever.
    
    This technique generates multiple query variations and combines results 
    using reciprocal rank fusion for improved relevance.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's QueryFusionRetriever.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(f"Retrieving chunks for {self.doc_id} using LlamaIndex QueryFusionRetriever.")

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

            # Create LlamaIndex QueryFusionRetriever
            fusion_retriever = QueryFusionRetriever(
                [base_retriever],  # List of retrievers to use for fusion
                similarity_top_k=self.top_k,
                num_queries=4,  # Number of query variations to generate
                use_async=False,
                verbose=False,
                llm=self.llm,  # Use the LLM to generate query variations
            )

            # Retrieve nodes using fusion technique
            nodes = fusion_retriever.retrieve(self.prompt)

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

            logger.info(f"Successfully retrieved {len(chunks)} chunks using fusion.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during fusion retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error during fusion retrieval for {self.doc_id}: {e}")
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
