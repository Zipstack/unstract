import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.retrievers.bm25 import BM25Retriever

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class RouterRetriever(BaseRetriever):
    """Router retrieval class using LlamaIndex's native RouterQueryEngine.

    This technique intelligently routes queries to different retrieval strategies
    based on query analysis.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's RouterQueryEngine.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using LlamaIndex RouterQueryEngine."
            )

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Create metadata filters for doc_id
            filters = MetadataFilters(
                filters=[
                    ExactMatchFilter(key="doc_id", value=self.doc_id),
                ],
            )

            # Create query engines for different strategies
            vector_query_engine = vector_store_index.as_query_engine(
                similarity_top_k=self.top_k,
                filters=filters,
            )

            # If LLM is available, create router with multiple strategies
            if self.llm:
                # Define query engine tools
                query_engine_tools = [
                    QueryEngineTool(
                        query_engine=vector_query_engine,
                        metadata=ToolMetadata(
                            name="vector_search",
                            description=(
                                "Useful for semantic similarity search, conceptual questions, "
                                "and finding information based on meaning and context."
                            ),
                        ),
                    ),
                ]

                # Try to add BM25 for keyword search
                try:
                    # Get nodes for BM25
                    temp_retriever = vector_store_index.as_retriever(
                        similarity_top_k=100,
                        filters=filters,
                    )
                    all_nodes = temp_retriever.retrieve("")

                    if all_nodes and len(all_nodes) > 10:
                        # Create BM25 retriever
                        bm25_retriever = BM25Retriever.from_defaults(
                            nodes=[node.node for node in all_nodes],
                            similarity_top_k=self.top_k,
                        )

                        # Create a query engine wrapper for BM25
                        bm25_query_engine = vector_store_index.as_query_engine(
                            retriever=bm25_retriever,
                        )

                        query_engine_tools.append(
                            QueryEngineTool(
                                query_engine=bm25_query_engine,
                                metadata=ToolMetadata(
                                    name="keyword_search",
                                    description=(
                                        "Best for finding specific terms, names, IDs, or exact phrases. "
                                        "Use when looking for precise keyword matches."
                                    ),
                                ),
                            )
                        )
                except Exception as e:
                    logger.debug(f"Could not create BM25 engine: {e}")

                # Create router query engine
                router_query_engine = RouterQueryEngine(
                    selector=LLMSingleSelector.from_defaults(llm=self.llm),
                    query_engine_tools=query_engine_tools,
                    verbose=False,
                )

                # Query using router
                response = router_query_engine.query(self.prompt)

                # Extract source nodes from response
                chunks: set[str] = set()
                if hasattr(response, "source_nodes"):
                    for node in response.source_nodes:
                        if node.score > 0:
                            chunks.add(node.get_content())
                        else:
                            logger.info(
                                f"Node score is less than 0. "
                                f"Ignored: {node.node_id} with score {node.score}"
                            )

                if chunks:
                    logger.info(
                        f"Successfully retrieved {len(chunks)} chunks using router."
                    )
                    return chunks

            # Fallback to simple vector retrieval
            vector_retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=filters,
            )

            nodes = vector_retriever.retrieve(self.prompt)
            chunks: set[str] = set()
            for node in nodes:
                if node.score > 0:
                    chunks.add(node.get_content())

            logger.info(
                f"Successfully retrieved {len(chunks)} chunks using vector retrieval."
            )
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during router retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during router retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
