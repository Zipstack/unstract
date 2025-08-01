import logging

from llama_index.core.query_engine import SubQuestionQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class SubquestionRetriever(BaseRetriever):
    """SubquestionRetrieval class for querying VectorDB using LlamaIndex's
    SubQuestionQueryEngine.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks from the VectorDB based on the provided prompt.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info("Initialising vector query engine...")
            vector_query_engine = self.vector_db.get_vector_store_index().as_query_engine(
                llm=self.llm, similarity_top_k=self.top_k
            )
            logger.info(
                f"Retrieving chunks for {self.doc_id} using SubQuestionQueryEngine."
            )
            query_engine_tools = [
                QueryEngineTool(
                    query_engine=vector_query_engine,
                    metadata=ToolMetadata(
                        name=self.doc_id, description=f"Nodes for {self.doc_id}"
                    ),
                ),
            ]
            query_bundle = QueryBundle(query_str=self.prompt)

            query_engine = SubQuestionQueryEngine.from_defaults(
                query_engine_tools=query_engine_tools,
                use_async=True,
                llm=self.llm,
            )

            response = query_engine.query(str_or_query_bundle=query_bundle)

            chunks: set[str] = {node.text for node in response.source_nodes}
            logger.info(f"Successfully retrieved {len(chunks)} chunks.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during retrieving chunks {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error during retrieving chunks {self.doc_id}: {e}")
            raise RetrievalError(f"Unexpected error: {str(e)}") from e
