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
        self._llm: LLM | None = llm
        self._retriever_llm: RetrieverLLM | None = None

    @property
    def llm(self) -> RetrieverLLM | None:
        """Return a llama-index compatible LLM, lazily created on first access.

        Avoids the cost of RetrieverLLM construction (adapter init,
        CallbackManager setup) for retrievers that never use the LLM
        (Simple, Automerging, Recursive).
        """
        if self._llm is None:
            return None
        if self._retriever_llm is None:
            self._retriever_llm = RetrieverLLM(llm=self._llm)
        return self._retriever_llm

    @staticmethod
    def retrieve() -> set[str]:
        return set()
