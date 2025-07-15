import logging

# Updated imports compatible with latest LlamaIndex structure
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.retrievers import RouterRetriever

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class QueryRouterRetriever(BaseRetriever):
    """Router Retriever that intelligently selects the most appropriate retrieval method.

    This retriever uses LlamaIndex's RouterRetriever to dynamically choose between
    different retrieval strategies based on query characteristics.
    """

    def __init__(self, *args, retriever_descriptions: dict[str, str] = None, **kwargs):
        """Initialize the QueryRouterRetriever.

        Args:
            *args: Arguments to pass to the parent class.
            retriever_descriptions: Descriptions for each retriever to help the router.
            **kwargs: Keyword arguments to pass to the parent class.
        """
        super().__init__(*args, **kwargs)

        # Default descriptions if none provided
        self.retriever_descriptions = retriever_descriptions or {
            "semantic": "Useful for semantic similarity and conceptual queries.",
            "keyword": "Useful for keyword matching and specific term searches.",
            "hybrid": "Useful for complex queries requiring both semantic and keyword matching.",
        }

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using the most appropriate retrieval strategy.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Routing retrieval for prompt: {self.prompt} with doc_id: {self.doc_id}"
            )

            # Get vector store index
            vector_index = self.vector_db.get_vector_store_index()

            # Common filter for all retrievers
            doc_filter = MetadataFilters(
                filters=[
                    ExactMatchFilter(key="doc_id", value=self.doc_id),
                ],
            )

            # Create different types of retrievers with the same filters
            # Semantic (vector) retriever
            vector_retriever = vector_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=doc_filter,
            )

            # Keyword (BM25) retriever
            from llama_index.retrievers import BM25Retriever

            keyword_retriever = BM25Retriever(
                index=vector_index, similarity_top_k=self.top_k
            )

            # Hybrid retriever
            from llama_index.retrievers import QueryFusionRetriever

            hybrid_retriever = QueryFusionRetriever(
                retrievers=[vector_retriever, keyword_retriever],
                similarity_top_k=self.top_k,
                use_original_query=True,
            )

            # Create the router retriever
            retriever_dict = {
                "semantic": vector_retriever,
                "keyword": keyword_retriever,
                "hybrid": hybrid_retriever,
            }

            # Create the router with descriptions
            router_retriever = RouterRetriever(
                retrievers=retriever_dict,
                llm=self.llm,  # Need LLM to make routing decisions
                retriever_descriptions=self.retriever_descriptions,
                select_multi=False,  # Just select one optimal retriever
            )

            # Retrieve nodes using the router
            nodes = router_retriever.retrieve(self.prompt)

            # Extract content from nodes
            context = set()
            for node in nodes:
                if hasattr(node, "score") and node.score > 0:
                    context.add(node.get_content())
                else:
                    # Some nodes might not have scores depending on retriever
                    context.add(node.get_content())

            logger.info(
                f"Successfully retrieved {len(context)} chunks using Router Retriever."
            )
            return context

        except Exception as e:
            logger.error(f"Error during router retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
