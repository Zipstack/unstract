from typing import Any

from unstract.flags.feature_flag import check_feature_flag_status
from unstract.prompt_service.constants import PromptServiceConstants as PSKeys
from unstract.prompt_service.core.retrievers.simple import SimpleRetriever
from unstract.prompt_service.core.retrievers.subquestion import SubquestionRetriever
from unstract.prompt_service.utils.file_utils import FileUtils

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.llm import LLM
    from unstract.sdk1.vector_db import VectorDB
else:
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
        if retrieval_type == PSKeys.SUBQUESTION:
            context = SubquestionRetriever(
                vector_db=vector_db, doc_id=doc_id, prompt=prompt, top_k=top_k, llm=llm
            ).retrieve()
        if retrieval_type == PSKeys.SIMPLE:
            context = SimpleRetriever(
                vector_db=vector_db, doc_id=doc_id, prompt=prompt, top_k=top_k
            ).retrieve()

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
