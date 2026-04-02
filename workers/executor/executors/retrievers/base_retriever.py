from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from unstract.sdk1.llm import LLM
    from unstract.sdk1.vector_db import VectorDB

from executor.executors.retrievers.retriever_llm import RetrieverLLM


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

        Avoids the cost of RetrieverLLM construction for retrievers that
        never use the LLM (Simple, Automerging, Recursive).
        """
        if self._llm is None:
            return None
        if self._retriever_llm is None:
            self._retriever_llm = RetrieverLLM(llm=self._llm)
        return self._retriever_llm

    def require_llm(self) -> RetrieverLLM:
        """Return the llama-index LLM or raise if not configured.

        Call this in retrievers that need an LLM (KeywordTable, Fusion,
        Subquestion) to fail early with a clear message instead of
        letting llama-index silently fall back to its default OpenAI LLM.
        """
        llm = self.llm
        if llm is None:
            raise ValueError(
                f"{type(self).__name__} requires an LLM. "
                "Pass llm= when constructing the retriever."
            )
        return llm

    @staticmethod
    def retrieve() -> set[str]:
        return set()
