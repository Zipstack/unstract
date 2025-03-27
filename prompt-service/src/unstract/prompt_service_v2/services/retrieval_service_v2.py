from typing import Any

from flask import current_app as app
from unstract.prompt_service_v2.helper.retrieval_helper import RetrievalHelper
from unstract.prompt_service_v2.services.answer_prompt_service import (
    AnswerPromptService,
)
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
    ) -> tuple[str, set[str]]:
        context: set[str] = set()
        app.logger.info(f"retrieinvg context.. {file_path}")
        if chunk_size == 0:
            context = RetrievalHelper.retrieve_complete_context(
                execution_source=execution_source, file_path=file_path
            )
        else:
            app.logger.info("into non zero chunk")
            context = RetrievalHelper.run_retrieval(
                output=output,
                doc_id=doc_id,
                llm=llm,
                vector_db=vector_db,
                retrieval_type=retrieval_type,
            )
        answer = AnswerPromptService.construct_and_run_prompt(  # type:ignore
            tool_settings=tool_settings,
            output=output,
            llm=llm,
            context="".join(context),
            prompt="promptx",
            metadata=metadata,
            execution_source=execution_source,
        )

        return answer, context
