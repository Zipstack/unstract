import logging

from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

# Updated imports compatible with latest LlamaIndex structure
from llama_index.retrievers import RecursiveRetriever
from llama_index.schema import IndexNode

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class RecursiveNodeRetriever(BaseRetriever):
    """Recursive Retriever class for advanced document retrieval.

    This retriever uses LlamaIndex's RecursiveRetriever to recursively retrieve
    related documents based on references within the initial retrieved nodes.
    """

    def __init__(self, *args, recursive_depth: int = 1, **kwargs):
        """Initialize the RecursiveNodeRetriever.

        Args:
            *args: Arguments to pass to the parent class.
            recursive_depth: The maximum depth for recursive retrieval.
            **kwargs: Keyword arguments to pass to the parent class.
        """
        super().__init__(*args, **kwargs)
        self.recursive_depth = recursive_depth

    def retrieve(self) -> set[str]:
        """Retrieve text chunks with recursive retrieval.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving context recursively for prompt: {self.prompt} "
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

            # Define a function to get child nodes based on a parent node
            def get_child_nodes_fn(parent_node: IndexNode):
                # Extract content and create a more specific query based on the parent
                parent_content = parent_node.get_content()
                # Filter query to related content - could use LLM to refine this further
                refined_query = f"context: {parent_content[:200]} question: {self.prompt}"

                # Retrieve related nodes
                child_nodes = base_retriever.retrieve(refined_query)
                return child_nodes

            # Create the recursive retriever
            recursive_retriever = RecursiveRetriever(
                retriever=base_retriever,
                get_child_nodes_fn=get_child_nodes_fn,
                max_depth=self.recursive_depth,
            )

            # Retrieve nodes
            retrieved_nodes = recursive_retriever.retrieve(self.prompt)

            # Extract content from nodes
            context = set()
            for node in retrieved_nodes:
                if hasattr(node, "score") and node.score > 0:
                    context.add(node.get_content())
                else:
                    # Some nodes from recursive retrieval might not have scores
                    context.add(node.get_content())

            logger.info(
                f"Successfully retrieved {len(context)} chunks using Recursive Retriever."
            )
            return context

        except Exception as e:
            logger.error(f"Error during recursive retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
