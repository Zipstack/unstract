"""Retrieval service — factory for retriever strategies.

Lazy-imports retriever classes to avoid llama_index/protobuf conflicts
at test-collection time. Same pattern as _get_indexing_deps() in Phase 2C.
"""

import datetime
import logging
from typing import Any

from executor.executors.constants import RetrievalStrategy

logger = logging.getLogger(__name__)


class RetrievalService:
    @staticmethod
    def _get_retriever_map() -> dict:
        """Lazy-import all retriever classes.

        Returns dict mapping strategy string to class.
        Wrapped in a method so tests can mock it.
        """
        from executor.executors.retrievers.automerging import AutomergingRetriever
        from executor.executors.retrievers.fusion import FusionRetriever
        from executor.executors.retrievers.keyword_table import KeywordTableRetriever
        from executor.executors.retrievers.recursive import RecursiveRetrieval
        from executor.executors.retrievers.router import RouterRetriever
        from executor.executors.retrievers.simple import SimpleRetriever
        from executor.executors.retrievers.subquestion import SubquestionRetriever

        return {
            RetrievalStrategy.SIMPLE.value: SimpleRetriever,
            RetrievalStrategy.SUBQUESTION.value: SubquestionRetriever,
            RetrievalStrategy.FUSION.value: FusionRetriever,
            RetrievalStrategy.RECURSIVE.value: RecursiveRetrieval,
            RetrievalStrategy.ROUTER.value: RouterRetriever,
            RetrievalStrategy.KEYWORD_TABLE.value: KeywordTableRetriever,
            RetrievalStrategy.AUTOMERGING.value: AutomergingRetriever,
        }

    @staticmethod
    def run_retrieval(
        output: dict[str, Any],
        doc_id: str,
        llm: Any,
        vector_db: Any,
        retrieval_type: str,
        context_retrieval_metrics: dict[str, Any] | None = None,
    ) -> list[str]:
        """Factory: instantiate and execute the retriever for the given strategy."""
        from executor.executors.constants import PromptServiceConstants as PSKeys

        prompt = output[PSKeys.PROMPTX]
        top_k = output[PSKeys.SIMILARITY_TOP_K]
        prompt_key = output.get(PSKeys.NAME, "<unknown>")
        start = datetime.datetime.now()

        retriever_map = RetrievalService._get_retriever_map()
        retriever_class = retriever_map.get(retrieval_type)
        if not retriever_class:
            raise ValueError(f"Unknown retrieval type: {retrieval_type}")

        retriever = retriever_class(
            vector_db=vector_db,
            doc_id=doc_id,
            prompt=prompt,
            top_k=top_k,
            llm=llm,
        )
        context = retriever.retrieve()

        elapsed = (datetime.datetime.now() - start).total_seconds()
        if context_retrieval_metrics is not None:
            context_retrieval_metrics[prompt_key] = {"time_taken(s)": elapsed}

        logger.info(
            "[Retrieval] prompt='%s' doc_id=%s strategy='%s' top_k=%d "
            "chunks=%d time=%.3fs",
            prompt_key,
            doc_id,
            retrieval_type,
            top_k,
            len(context),
            elapsed,
        )
        return list(context)

    @staticmethod
    def retrieve_complete_context(
        execution_source: str,
        file_path: str,
        context_retrieval_metrics: dict[str, Any] | None = None,
        prompt_key: str = "<unknown>",
    ) -> list[str]:
        """Load full file content for chunk_size=0 retrieval."""
        from executor.executors.file_utils import FileUtils

        fs = FileUtils.get_fs_instance(execution_source=execution_source)
        start = datetime.datetime.now()
        content = fs.read(path=file_path, mode="r")
        elapsed = (datetime.datetime.now() - start).total_seconds()

        if context_retrieval_metrics is not None:
            context_retrieval_metrics[prompt_key] = {"time_taken(s)": elapsed}

        logger.info(
            "[Retrieval] prompt='%s' complete_context chars=%d time=%.3fs",
            prompt_key,
            len(content),
            elapsed,
        )
        return [content]
