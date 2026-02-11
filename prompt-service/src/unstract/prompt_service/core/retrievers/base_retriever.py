from llama_index.llms.litellm import LiteLLM as LlamaIndexLiteLLM
from unstract.prompt_service.utils.llm_helper import get_llama_index_llm
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
        self.llm = llm if llm else None
        self._llama_index_llm: LlamaIndexLiteLLM | None = None

    @property
    def llama_index_llm(self) -> LlamaIndexLiteLLM | None:
        """Return a llama-index compatible LLM, lazily created from SDK1 LLM.

        Llama-index components (KeywordTableIndex, SubQuestionQueryEngine,
        etc.) expect an instance of ``llama_index.core.llms.llm.LLM``.
        SDK1's ``LLM`` wraps litellm directly and is *not* compatible.
        This property bridges the gap.
        """
        if self._llama_index_llm is None and self.llm is not None:
            self._llama_index_llm = get_llama_index_llm(self.llm)
        return self._llama_index_llm

    @staticmethod
    def retrieve() -> set[str]:
        return set()
