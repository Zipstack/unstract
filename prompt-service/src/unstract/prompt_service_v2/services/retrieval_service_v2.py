from typing import Any

from unstract.prompt_service_v2.helper.retrieval_helper import RetrievalHelper
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
    ) -> set[str]:
        context: set[str] = set()

        if chunk_size == 0:
            context = RetrievalHelper.retrieve_complete_context(
                execution_source=execution_source, file_path=file_path
            )
        else:
            context = RetrievalHelper.run_retrieval(
                tool_settings=tool_settings,
                output=output,
                doc_id=doc_id,
                llm=llm,
                vector_db=vector_db,
                retrieval_type=retrieval_type,
                metadata=metadata,
                execution_source=execution_source,
            )

        return context
