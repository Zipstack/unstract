from typing import Any, Optional

from unstract.prompt_service_v2.constants import PromptServiceConstants as PSKeys
from unstract.prompt_service_v2.core.retrievers.simple import SimpleRetriever
from unstract.prompt_service_v2.core.retrievers.subquestion import SubquestionRetriever
from unstract.prompt_service_v2.services.answer_prompt_service import (
    AnswerPromptService,
)
from unstract.prompt_service_v2.utils.file_utils import FileUtils
from unstract.sdk.llm import LLM
from unstract.sdk.vector_db import VectorDB


class RetrievalHelper:
    @staticmethod
    def run_retrieval(  # type:ignore
        tool_settings: dict[str, Any],
        output: dict[str, Any],
        doc_id: str,
        llm: LLM,
        vector_db: VectorDB,
        retrieval_type: str,
        metadata: dict[str, Any],
        execution_source: Optional[str] = None,
    ) -> tuple[str, set[str]]:
        context: set[str] = set()
        prompt = output[PSKeys.PROMPTX]
        top_k = output[PSKeys.SIMILARITY_TOP_K]
        if retrieval_type == PSKeys.SUBQUESTION:
            context = SubquestionRetriever(
                vector_db=vector_db, doc_id=doc_id, prompt=prompt, top_k=top_k
            ).retrieve()
        if retrieval_type == PSKeys.SIMPLE:
            context = SimpleRetriever(
                vector_db=vector_db, doc_id=doc_id, prompt=prompt, top_k=top_k
            ).retrieve()

        answer = AnswerPromptService.construct_and_run_prompt(  # type:ignore
            tool_settings=tool_settings,
            output=output,
            llm=llm,
            context="\n".join(context),
            prompt="promptx",
            metadata=metadata,
            execution_source=execution_source,
        )

        return (answer, context)

    def retrieve_complete_context(self, execution_source: str, file_path: str) -> str:
        """
        Loads full context from raw file for zero chunk size retrieval
        Args:
            path (str): Path to the directory containing text file.

        Returns:
            str: context from extracted file.
        """
        fs_instance = FileUtils.get_fs_instance(execution_source=execution_source)
        return fs_instance.read(path=file_path, mode="r")
