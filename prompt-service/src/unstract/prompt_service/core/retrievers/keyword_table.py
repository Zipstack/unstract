import logging

# Updated imports compatible with latest LlamaIndex structure
from llama_index import QueryBundle
from llama_index.indices import KeywordTableIndex

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class KeywordTableRetriever(BaseRetriever):
    """Keyword Table Retriever for precise keyword-based document matching.

    This retriever uses LlamaIndex's KeywordTableIndex for efficient keyword-based
    retrieval, which can be particularly effective for technical content and
    precise term matching scenarios.
    """

    def __init__(
        self,
        *args,
        keyword_extract_mode: str = "default",
        max_keywords_per_chunk: int = 10,
        **kwargs,
    ):
        """Initialize the KeywordTableRetriever.

        Args:
            *args: Arguments to pass to the parent class.
            keyword_extract_mode: Mode for keyword extraction ('default', 'rake', or 'llm').
            max_keywords_per_chunk: Maximum number of keywords to extract per chunk.
            **kwargs: Keyword arguments to pass to the parent class.
        """
        super().__init__(*args, **kwargs)
        self.keyword_extract_mode = keyword_extract_mode
        self.max_keywords_per_chunk = max_keywords_per_chunk

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using keyword-based matching.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Performing keyword-based retrieval for prompt: {self.prompt} "
                f"with doc_id: {self.doc_id}"
            )

            # Get vector store index
            vector_index = self.vector_db.get_vector_store_index()

            # Get all nodes for this document
            all_nodes = []

            for node_id, node in vector_index.docstore.docs.items():
                if (
                    hasattr(node, "metadata")
                    and node.metadata.get("doc_id") == self.doc_id
                ):
                    all_nodes.append(node)

            logger.info(f"Found {len(all_nodes)} nodes for document ID {self.doc_id}")

            if not all_nodes:
                logger.warning(f"No nodes found for document ID {self.doc_id}")
                return set()

            # Create a keyword table index from these nodes
            keyword_index = KeywordTableIndex(
                nodes=all_nodes, max_keywords_per_chunk=self.max_keywords_per_chunk
            )

            # Create a retriever from the keyword index
            keyword_retriever = keyword_index.as_retriever(similarity_top_k=self.top_k)

            # Create query bundle to handle complex queries
            query_bundle = QueryBundle(query_str=self.prompt)

            # Retrieve nodes
            nodes = keyword_retriever.retrieve(query_bundle)

            # Extract content from nodes
            context = set()
            for node in nodes:
                if hasattr(node, "score") and node.score > 0:
                    context.add(node.get_content())
                else:
                    # Some keyword matches might not have scores
                    context.add(node.get_content())

            logger.info(
                f"Successfully retrieved {len(context)} chunks using Keyword Table Retriever."
            )
            return context

        except Exception as e:
            logger.error(f"Error during keyword table retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
