import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import AutoMergingRetriever as LlamaAutoMergingRetriever
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class AutomergingRetriever(BaseRetriever):
    """Automerging retrieval using LlamaIndex's native AutoMergingRetriever.

    This retriever merges smaller chunks into larger ones when the smaller chunks
    don't contain enough information, providing better context for answers.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's native AutoMergingRetriever.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using LlamaIndex AutoMergingRetriever."
            )

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Create base vector retriever with metadata filters
            base_retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Try to use native AutoMergingRetriever
            try:
                # Create AutoMergingRetriever with the base retriever
                auto_merging_retriever = LlamaAutoMergingRetriever(
                    base_retriever,
                    storage_context=self.vector_db.get_storage_context()
                    if hasattr(self.vector_db, "get_storage_context")
                    else None,
                    verbose=False,
                )

                # Retrieve nodes using auto-merging
                nodes = auto_merging_retriever.retrieve(self.prompt)

            except Exception as e:
                logger.error(f"AutoMergingRetriever failed : {e}")
                raise RetrievalError(f"AutoMergingRetriever failed: {str(e)}") from e

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
                f"Successfully retrieved {len(chunks)} chunks using AutoMergingRetriever."
            )
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during auto-merging retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during auto-merging retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
