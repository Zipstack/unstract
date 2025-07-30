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

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using LlamaIndex's RouterQueryEngine.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(f"Retrieving chunks for {self.doc_id} using LlamaIndex RouterQueryEngine.")

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Create base retrievers with metadata filters
            vector_retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Create query engines for different strategies
            vector_query_engine = vector_store_index.as_query_engine(
                similarity_top_k=self.top_k,
                llm=self.llm,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Define query engine tools for router
            query_engine_tools = [
                QueryEngineTool(
                    query_engine=vector_query_engine,
                    metadata=ToolMetadata(
                        name="vector_search",
                        description="Useful for semantic similarity search and general questions about the document content."
                    ),
                ),
            ]

            # Create router query engine if LLM is available
            if self.llm:
                router_query_engine = RouterQueryEngine(
                    selector=LLMSingleSelector.from_defaults(llm=self.llm),
                    query_engine_tools=query_engine_tools,
                    verbose=False,
                )
                
                # Query using router
                response = router_query_engine.query(self.prompt)
                
                # Extract source nodes from response
                chunks: set[str] = set()
                if hasattr(response, 'source_nodes'):
                    for node in response.source_nodes:
                        if node.score > 0:
                            chunks.add(node.get_content())
                        else:
                            logger.info(
                                f"Node score is less than 0. "
                                f"Ignored: {node.node_id} with score {node.score}"
                            )
            else:
                # Fallback to simple vector retrieval if no LLM
                nodes = vector_retriever.retrieve(self.prompt)
                chunks: set[str] = set()
                for node in nodes:
                    if node.score > 0:
                        chunks.add(node.get_content())
                    else:
                        logger.info(
                            f"Node score is less than 0. "
                            f"Ignored: {node.node_id} with score {node.score}"
                        )

            logger.info(f"Successfully retrieved {len(chunks)} chunks using router.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during router retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error during router retrieval for {self.doc_id}: {e}")
            raise RetrievalError(f"Unexpected error: {str(e)}") from e