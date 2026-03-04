from unstract.prompt_service.core.retrievers.retriever_llm import RetrieverLLM
from unstract.sdk1.llm import LLM
from unstract.sdk1.vector_db import VectorDB


class BaseRetriever:
    def __init__(
        self,
        vector_db: VectorDB,
        prompt: str,
        doc_id: str,
        top_k: int,
        llm: LLM | None = None,
    ):
        """Initialize the Retrieval class.

        Args:
            vector_db (VectorDB): The vector database instance.
            prompt (str): The query prompt.
            doc_id (str): Document identifier for query context.
            top_k (int): Number of top results to retrieve.
        """
        self.vector_db = vector_db
        self.prompt = prompt
        self.doc_id = doc_id
        self.top_k = top_k
        self.llm: RetrieverLLM | None = self._get_llm(llm)

    @staticmethod
    def _get_llm(llm: LLM | None) -> RetrieverLLM | None:
        """Convert SDK1 LLM to a llama-index compatible RetrieverLLM.

        Llama-index components (KeywordTableIndex, SubQuestionQueryEngine,
        etc.) expect an instance of ``llama_index.core.llms.llm.LLM``.
        SDK1's ``LLM`` wraps litellm directly and is *not* compatible.
        """
        return RetrieverLLM(llm=llm) if llm else None

    @staticmethod
    def retrieve() -> set[str]:
        return set()
