import logging

from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

# Updated imports compatible with latest LlamaIndex structure
from llama_index.retrievers import AutoMergingRetriever

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class MergingRetriever(BaseRetriever):
    """AutoMerging Retriever that consolidates similar content during retrieval.

    This retriever uses LlamaIndex's AutoMergingRetriever to automatically merge
    similar chunks during retrieval for more comprehensive context.
    """

    def __init__(
        self,
        *args,
        similarity_threshold: float = 0.7,
        collapse_nodes: bool = True,
        **kwargs,
    ):
        """Initialize the MergingRetriever.

        Args:
            *args: Arguments to pass to the parent class.
            similarity_threshold: Threshold for considering chunks as similar (0-1).
            collapse_nodes: Whether to collapse similar nodes into one.
            **kwargs: Keyword arguments to pass to the parent class.
        """
        super().__init__(*args, **kwargs)
        self.similarity_threshold = similarity_threshold
        self.collapse_nodes = collapse_nodes

    def retrieve(self) -> set[str]:
        """Retrieve and merge similar text chunks.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Auto-merging retrieval for prompt: {self.prompt} "
                f"with doc_id: {self.doc_id}"
            )

            # Get vector store index
            vector_index = self.vector_db.get_vector_store_index()

            # Create base retriever with document filters
            base_retriever = vector_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Create auto-merging retriever
            auto_merging_retriever = AutoMergingRetriever(
                base_retriever,
                similarity_threshold=self.similarity_threshold,
                rerank=True,  # Rerank results after merging
                verbose=True,  # Enable verbose mode for debugging
                collapse_nodes=self.collapse_nodes,
                llm=self.llm,
            )

            # Retrieve nodes
            nodes = auto_merging_retriever.retrieve(self.prompt)

            # Extract content from nodes
            context = set()
            for node in nodes:
                if hasattr(node, "score") and node.score > 0:
                    context.add(node.get_content())
                else:
                    # Some nodes might not have scores after merging
                    context.add(node.get_content())

            logger.info(
                f"Successfully retrieved {len(context)} merged chunks using AutoMerging Retriever."
            )
            return context

        except Exception as e:
            logger.error(f"Error during auto-merging retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
