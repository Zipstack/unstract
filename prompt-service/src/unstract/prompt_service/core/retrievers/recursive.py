import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.indices.query.query_transform import HyDEQueryTransform
from llama_index.core.query_engine import TransformQueryEngine
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class RecursiveRetrieval(BaseRetriever):
    """Recursive retrieval using LlamaIndex's HyDE (Hypothetical Document Embeddings).

    This generates a hypothetical document for the query and uses it to find
    more relevant chunks, effectively doing a form of recursive refinement.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using HyDE query transformation.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using HyDE recursive approach."
            )

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

            # If we have an LLM, use HyDE for enhanced retrieval
            if self.llm:
                try:
                    # Create HyDE query transform
                    hyde = HyDEQueryTransform(llm=self.llm, include_original=True)

                    # Create query engine with transform
                    query_engine = vector_store_index.as_query_engine(
                        similarity_top_k=self.top_k,
                        filters=MetadataFilters(
                            filters=[
                                ExactMatchFilter(key="doc_id", value=self.doc_id),
                            ],
                        ),
                    )

                    # Transform query engine with HyDE
                    transformed_query_engine = TransformQueryEngine(query_engine, hyde)

                    # Query and get response
                    response = transformed_query_engine.query(self.prompt)

                    # Extract chunks from source nodes
                    chunks: set[str] = set()
                    if hasattr(response, "source_nodes"):
                        for node in response.source_nodes:
                            if node.score > 0:
                                chunks.add(node.get_content())

                    if chunks:
                        logger.info(
                            f"Successfully retrieved {len(chunks)} chunks using HyDE."
                        )
                        return chunks
                except Exception as e:
                    logger.warning(
                        f"HyDE retrieval failed, falling back to standard: {e}"
                    )

            # Fallback to standard retrieval
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

            logger.info(f"Successfully retrieved {len(chunks)} chunks.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during recursive retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during recursive retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
