import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class RouterRetriever(BaseRetriever):
    """Router retrieval class using LlamaIndex's native RouterQueryEngine.

    This technique intelligently routes queries to different retrieval strategies
    based on query analysis.
    """

    def _create_metadata_filters(self):
        """Create metadata filters for doc_id."""
        return MetadataFilters(
            filters=[
                ExactMatchFilter(key="doc_id", value=self.doc_id),
            ],
        )

    def _create_base_query_engine(self, vector_store_index, filters):
        """Create the base vector query engine."""
        return vector_store_index.as_query_engine(
            similarity_top_k=self.top_k,
            filters=filters,
            llm=self.llm,
        )

    def _add_keyword_search_tool(self, query_engine_tools, vector_store_index, filters):
        """Add keyword search tool to query engine tools list."""
        try:
            keyword_query_engine = vector_store_index.as_query_engine(
                similarity_top_k=self.top_k * 2,
                filters=filters,
                llm=self.llm,
            )
            query_engine_tools.append(
                QueryEngineTool(
                    query_engine=keyword_query_engine,
                    metadata=ToolMetadata(
                        name="keyword_search",
                        description=(
                            "Best for finding specific terms, names, numbers, dates, "
                            "or exact phrases. Use when looking for precise matches."
                        ),
                    ),
                )
            )
        except Exception as e:
            logger.debug(f"Could not create keyword search engine: {e}")

    def _add_broad_search_tool(self, query_engine_tools, vector_store_index, filters):
        """Add broad search tool to query engine tools list."""
        try:
            broad_query_engine = vector_store_index.as_query_engine(
                similarity_top_k=self.top_k * 3,
                filters=filters,
                llm=self.llm,
            )
            query_engine_tools.append(
                QueryEngineTool(
                    query_engine=broad_query_engine,
                    metadata=ToolMetadata(
                        name="broad_search",
                        description=(
                            "Useful for general questions, exploratory queries, "
                            "or when you need comprehensive information on a topic."
                        ),
                    ),
                )
            )
        except Exception as e:
            logger.debug(f"Could not create broad search engine: {e}")

    def _extract_chunks_from_response(self, response):
        """Extract chunks from router query response."""
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
        return chunks

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's RouterQueryEngine.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using LlamaIndex RouterQueryEngine."
            )

            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()
            filters = self._create_metadata_filters()
            vector_query_engine = self._create_base_query_engine(vector_store_index, filters)

            if not self.llm:
                return set()

            # Create base query engine tools
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

            # Add additional search strategies
            self._add_keyword_search_tool(query_engine_tools, vector_store_index, filters)
            self._add_broad_search_tool(query_engine_tools, vector_store_index, filters)

            # Create and execute router query
            router_query_engine = RouterQueryEngine.from_defaults(
                selector=LLMSingleSelector.from_defaults(llm=self.llm),
                query_engine_tools=query_engine_tools,
                verbose=True,
                llm=self.llm,
            )

            response = router_query_engine.query(self.prompt)
            chunks = self._extract_chunks_from_response(response)

            logger.info(f"Successfully retrieved {len(chunks)} chunks using router.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during router retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during router retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
