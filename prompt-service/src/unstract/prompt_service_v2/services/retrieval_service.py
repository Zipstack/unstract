import time
from typing import Any, Optional

from flask import current_app as app
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from unstract.prompt_service.exceptions import APIError
from unstract.prompt_service_v2.constants import PromptServiceContants as PSKeys
from unstract.prompt_service_v2.constants import RunLevel
from unstract.prompt_service_v2.services.answer_prompt_service import (
    AnswerPromptService,
)
from unstract.prompt_service_v2.utils.log import publish_log
from unstract.sdk.constants import LogLevel
from unstract.sdk.exceptions import SdkError
from unstract.sdk.index import Index
from unstract.sdk.llm import LLM


class RetrievalService:

    @staticmethod
    def run_retrieval(  # type:ignore
        tool_settings: dict[str, Any],
        output: dict[str, Any],
        doc_id: str,
        llm: LLM,
        vector_index,
        retrieval_type: str,
        metadata: dict[str, Any],
        execution_source: Optional[str] = None,
    ) -> tuple[str, set[str]]:
        context: set[str] = set()
        prompt = output[PSKeys.PROMPTX]
        if retrieval_type == PSKeys.SUBQUESTION:
            subq_prompt: str = (
                f"I am sending you a verbose prompt \n \n Prompt : {prompt} \n \n"
                "Generate set of specific subquestions "
                "from the prompt which can be used to retrive "
                "relevant context from vector db. "
                "Use your logical abilities to "
                " only generate as many subquestions as necessary "
                " — fewer subquestions if the prompt is simpler. "
                "Decide the minimum limit for subquestions "
                "based on the complexity input prompt and set the maximum limit"
                "for the subquestions to 10."
                "Ensure that each subquestion is distinct and relevant"
                "to the the original query. "
                "Do not add subquestions for details"
                "not mentioned in the original prompt."
                " The goal is to maximize retrieval accuracy"
                " using these subquestions. Use your logical abilities to ensure "
                " that each subquestion targets a distinct aspect of the original"
                " query. Please note that, there are cases where the "
                "response might have a list of answers. The subquestions must not"
                " miss out any values in these cases. "
                "Output should be a list of comma seperated "
                "subquestion prompts. Do not change this format. \n \n "
                " Subquestions : "
            )
            subquestions = AnswerPromptService.run_completion(
                llm=llm,
                prompt=subq_prompt,
            )
            subquestion_list = subquestions.split(",")
            for each_subq in subquestion_list:
                retrieved_context = RetrievalService._retrieve_context(
                    output, doc_id, vector_index, each_subq
                )
                context.update(retrieved_context)

        if retrieval_type == PSKeys.SIMPLE:

            context = RetrievalService._retrieve_context(
                output, doc_id, vector_index, prompt
            )

            if not context:
                # UN-1288 For Pinecone, we are seeing an inconsistent case where
                # query with doc_id fails even though indexing just happened.
                # This causes the following retrieve to return no text.
                # To rule out any lag on the Pinecone vector DB write,
                # the following sleep is added
                # Note: This will not fix the issue. Since this issue is inconsistent
                # and not reproducible easily, this is just a safety net.
                time.sleep(2)
                context = RetrievalService._retrieve_context(
                    output, doc_id, vector_index, prompt
                )

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

    @staticmethod
    def _retrieve_context(output, doc_id, vector_index, answer) -> set[str]:
        retriever = vector_index.as_retriever(
            similarity_top_k=output[PSKeys.SIMILARITY_TOP_K],
            filters=MetadataFilters(
                filters=[
                    ExactMatchFilter(key="doc_id", value=doc_id),
                    # TODO: Enable after adding section in GUI
                    # ExactMatchFilter(
                    #     key="section", value=output["section"]
                ],
            ),
        )
        nodes = retriever.retrieve(answer)
        context: set[str] = set()
        for node in nodes:
            # ToDo: May have to fine-tune this value for node score or keep it
            # configurable at the adapter level
            if node.score > 0:
                context.add(node.get_content())
            else:
                app.logger.info(
                    "Node score is less than 0. "
                    f"Ignored: {node.node_id} with score {node.score}"
                )
        return context

    @staticmethod
    def fetch_context_from_vector_db(
        index: Index,
        output: dict[str, Any],
        doc_id: str,
        tool_id: str,
        doc_name: str,
        prompt_name: str,
        log_events_id: str,
        usage_kwargs: dict[str, Any],
    ) -> set[str]:
        """
        Fetches context from the index for the given document ID. Implements a retry
        mechanism with logging and raises an error if context retrieval fails.
        Args:
            index: The index object to query.
            output: Dictionary containing keys like embedding and vector DB instance ID.
            doc_id: The document ID to query.
            tool_id: Identifier for the tool in use.
            doc_name: Name of the document being queried.
            prompt_name: Name of the prompt being executed.
            log_events_id: Unique ID for logging events.
            usage_kwargs: Additional usage parameters.
        Raises:
            APIError: If context retrieval fails after retrying.
        """
        context: set[str] = set()
        try:
            retrieved_context = index.query_index(
                embedding_instance_id=output[PSKeys.EMBEDDING],
                vector_db_instance_id=output[PSKeys.VECTOR_DB],
                doc_id=doc_id,
                usage_kwargs=usage_kwargs,
            )

            if retrieved_context:
                context.add(retrieved_context)
                publish_log(
                    log_events_id,
                    {
                        "tool_id": tool_id,
                        "prompt_key": prompt_name,
                        "doc_name": doc_name,
                    },
                    LogLevel.DEBUG,
                    RunLevel.RUN,
                    "Fetched context from vector DB",
                )
            else:
                # Handle lag in vector DB write (e.g., Pinecone issue)
                time.sleep(2)
                retrieved_context = index.query_index(
                    embedding_instance_id=output[PSKeys.EMBEDDING],
                    vector_db_instance_id=output[PSKeys.VECTOR_DB],
                    doc_id=doc_id,
                    usage_kwargs=usage_kwargs,
                )

                if retrieved_context is None:
                    msg = PSKeys.NO_CONTEXT_ERROR
                    app.logger.error(
                        f"{msg} {output[PSKeys.VECTOR_DB]} for doc_id {doc_id}"
                    )
                    publish_log(
                        log_events_id,
                        {
                            "tool_id": tool_id,
                            "prompt_key": prompt_name,
                            "doc_name": doc_name,
                        },
                        LogLevel.ERROR,
                        RunLevel.RUN,
                        msg,
                    )
                    raise APIError(message=msg)
        except SdkError as e:
            msg = f"Unable to fetch context from vector DB. {str(e)}"
            app.logger.error(
                f"{msg}. VectorDB: {output[PSKeys.VECTOR_DB]}, doc_id: {doc_id}"
            )
            publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.ERROR,
                RunLevel.RUN,
                msg,
            )
            raise APIError(message=msg, code=e.status_code)
        return context
