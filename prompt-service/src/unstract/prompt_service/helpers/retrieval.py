from typing import Any

from unstract.prompt_service.constants import PromptServiceConstants as PSKeys
from unstract.prompt_service.constants import RetrievalStrategy
from unstract.prompt_service.core.retrievers.automerging import AutomergingRetriever
from unstract.prompt_service.core.retrievers.fusion import FusionRetriever
from unstract.prompt_service.core.retrievers.keyword_table import KeywordTableRetriever
from unstract.prompt_service.core.retrievers.recursive import RecursiveRetrieval
from unstract.prompt_service.core.retrievers.router import RouterRetriever
from unstract.prompt_service.core.retrievers.simple import SimpleRetriever
from unstract.prompt_service.core.retrievers.subquestion import SubquestionRetriever
from unstract.prompt_service.utils.file_utils import FileUtils
from unstract.sdk.llm import LLM
from unstract.sdk.vector_db import VectorDB


class RetrievalHelper:
    @staticmethod
    def run_retrieval(  # type:ignore
        output: dict[str, Any],
        doc_id: str,
        llm: LLM,
        vector_db: VectorDB,
        retrieval_type: str,
    ) -> set[str]:
        context: set[str] = set()
        prompt = output[PSKeys.PROMPTX]
        top_k = output[PSKeys.SIMILARITY_TOP_K]

        # Map retrieval type to retriever class
        retriever_map = {
            RetrievalStrategy.SIMPLE.value: SimpleRetriever,
            RetrievalStrategy.SUBQUESTION.value: SubquestionRetriever,
            RetrievalStrategy.FUSION.value: FusionRetriever,
            RetrievalStrategy.RECURSIVE.value: RecursiveRetrieval,
            RetrievalStrategy.ROUTER.value: RouterRetriever,
            RetrievalStrategy.KEYWORD_TABLE.value: KeywordTableRetriever,
            RetrievalStrategy.AUTOMERGING.value: AutomergingRetriever,
        }

        # Legacy support for old constant values
        if retrieval_type == PSKeys.SIMPLE:
            retrieval_type = RetrievalStrategy.SIMPLE.value
        elif retrieval_type == PSKeys.SUBQUESTION:
            retrieval_type = RetrievalStrategy.SUBQUESTION.value

        # Get the appropriate retriever class
        retriever_class = retriever_map.get(retrieval_type)
        if not retriever_class:
            raise ValueError(f"Unknown retrieval type: {retrieval_type}")

        # Create and execute retriever
        retriever = retriever_class(
            vector_db=vector_db,
            doc_id=doc_id,
            prompt=prompt,
            top_k=top_k,
            llm=llm,
        )
        context = retriever.retrieve()

        return context

    @staticmethod
    def retrieve_complete_context(execution_source: str, file_path: str) -> str:
        """Loads full context from raw file for zero chunk size retrieval
        Args:
            path (str): Path to the directory containing text file.

        Returns:
            str: context from extracted file.
        """
        fs_instance = FileUtils.get_fs_instance(execution_source=execution_source)
        return fs_instance.read(path=file_path, mode="r")
