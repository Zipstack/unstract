import datetime
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
from unstract.prompt_service.services.answer_prompt import AnswerPromptService
from unstract.prompt_service.utils.file_utils import FileUtils
from unstract.prompt_service.utils.metrics import Metrics
from unstract.sdk.llm import LLM
from unstract.sdk.vector_db import VectorDB


class RetrievalService:
    @staticmethod
    def perform_retrieval(  # type:ignore
        tool_settings: dict[str, Any],
        output: dict[str, Any],
        doc_id: str,
        llm: LLM,
        vector_db: VectorDB,
        retrieval_type: str,
        metadata: dict[str, Any],
        chunk_size: int,
        execution_source: str,
        file_path: str,
        context_retrieval_metrics: dict[str, Any],
    ) -> tuple[str, list[str]]:
        context: list[str]
        if chunk_size == 0:
            context = RetrievalService.retrieve_complete_context(
                execution_source=execution_source,
                file_path=file_path,
                context_retrieval_metrics=context_retrieval_metrics,
                prompt_key=output[PSKeys.PROMPTX],
            )
        else:
            context = RetrievalService.run_retrieval(
                output=output,
                doc_id=doc_id,
                llm=llm,
                vector_db=vector_db,
                retrieval_type=retrieval_type,
                context_retrieval_metrics=context_retrieval_metrics,
            )
        answer = AnswerPromptService.construct_and_run_prompt(  # type:ignore
            tool_settings=tool_settings,
            output=output,
            llm=llm,
            context="\n".join(context),
            prompt="promptx",
            metadata=metadata,
            execution_source=execution_source,
            file_path=file_path,
        )
        return answer, context

    @staticmethod
    def run_retrieval(  # type:ignore
        output: dict[str, Any],
        doc_id: str,
        llm: LLM,
        vector_db: VectorDB,
        retrieval_type: str,
        context_retrieval_metrics: dict[str, Any],
    ) -> list[str]:
        context: set[str]
        prompt = output[PSKeys.PROMPTX]
        top_k = output[PSKeys.SIMILARITY_TOP_K]
        prompt_key = output[PSKeys.NAME]
        retrieval_start_time = datetime.datetime.now()

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
        context_retrieval_metrics[prompt_key] = {
            "time_taken(s)": Metrics.elapsed_time(start_time=retrieval_start_time)
        }
        return list(context)

    @staticmethod
    def retrieve_complete_context(
        execution_source: str,
        file_path: str,
        context_retrieval_metrics: dict[str, Any],
        prompt_key: str,
    ) -> list[str]:
        """Loads full context from raw file for zero chunk size retrieval
        Args:
            execution_source (str): Source of execution.
            file_path (str): Path to the directory containing text file.

        Returns:
            list[str]: context from extracted file.
        """
        fs_instance = FileUtils.get_fs_instance(execution_source=execution_source)
        retrieval_start_time = datetime.datetime.now()
        context = fs_instance.read(path=file_path, mode="r")
        context_retrieval_metrics[prompt_key] = {
            "time_taken(s)": Metrics.elapsed_time(start_time=retrieval_start_time)
        }
        return [context]
