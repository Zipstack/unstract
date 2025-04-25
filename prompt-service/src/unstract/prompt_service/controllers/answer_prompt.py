"""Published API Controller"""

from typing import Any

from flask import Blueprint, request
from flask import current_app as app

from unstract.core.flask.exceptions import APIError
from unstract.prompt_service.constants import PromptServiceConstants as PSKeys
from unstract.prompt_service.constants import RunLevel
from unstract.prompt_service.exceptions import BadRequest
from unstract.prompt_service.helpers.auth import AuthHelper
from unstract.prompt_service.helpers.plugin import PluginManager
from unstract.prompt_service.helpers.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.prompt_service.helpers.usage import UsageHelper
from unstract.prompt_service.services.answer_prompt import AnswerPromptService
from unstract.prompt_service.services.retrieval import RetrievalService
from unstract.prompt_service.services.variable_replacement import (
    VariableReplacementService,
)
from unstract.prompt_service.utils.log import publish_log
from unstract.sdk.adapters.llm.no_op.src.no_op_custom_llm import NoOpCustomLLM
from unstract.sdk.constants import LogLevel
from unstract.sdk.embedding import Embedding
from unstract.sdk.exceptions import SdkError
from unstract.sdk.index import Index
from unstract.sdk.llm import LLM
from unstract.sdk.vector_db import VectorDB

answer_prompt_bp = Blueprint("answer-prompt", __name__)


@AuthHelper.auth_required
@answer_prompt_bp.route("/answer-prompt", methods=["POST"])
def prompt_processor() -> Any:
    platform_key = AuthHelper.get_token_from_auth_header(request)
    payload: dict[Any, Any] = request.json
    if not payload:
        raise BadRequest
    tool_settings = payload.get(PSKeys.TOOL_SETTINGS, {})
    enable_challenge = tool_settings.get(PSKeys.ENABLE_CHALLENGE, False)
    # Rename "outputs" to "prompts" in payload
    prompts = payload.get(PSKeys.OUTPUTS, [])
    tool_id: str = payload.get(PSKeys.TOOL_ID, "")
    run_id: str = payload.get(PSKeys.RUN_ID, "")
    execution_id: str = payload.get(PSKeys.EXECUTION_ID, "")
    file_hash = payload.get(PSKeys.FILE_HASH)
    file_path = payload.get(PSKeys.FILE_PATH)
    doc_name = str(payload.get(PSKeys.FILE_NAME, ""))
    log_events_id: str = payload.get(PSKeys.LOG_EVENTS_ID, "")
    structured_output: dict[str, Any] = {}
    metadata: dict[str, Any] = {
        PSKeys.RUN_ID: run_id,
        PSKeys.FILE_NAME: doc_name,
        PSKeys.CONTEXT: {},
        PSKeys.REQUIRED_FIELDS: {},
    }
    metrics: dict = {}
    variable_names: list[str] = []
    # Identifier for source of invocation
    execution_source = payload.get(PSKeys.EXECUTION_SOURCE, "")
    context_retrieval_metrics = {}
    publish_log(
        log_events_id,
        {"tool_id": tool_id, "run_id": run_id, "doc_name": doc_name},
        LogLevel.DEBUG,
        RunLevel.RUN,
        f"Preparing to execute {len(prompts)} prompt(s)",
    )
    # Rename "output" to "prompt"
    for output in prompts:  # type:ignore
        variable_names.append(output[PSKeys.NAME])
        metadata[PSKeys.REQUIRED_FIELDS][output[PSKeys.NAME]] = output.get(
            PSKeys.REQUIRED, None
        )

    for output in prompts:  # type:ignore
        prompt_name = output[PSKeys.NAME]
        prompt_text = output[PSKeys.PROMPT]
        chunk_size = output[PSKeys.CHUNK_SIZE]
        app.logger.info(f"[{tool_id}] chunk size: {chunk_size}")
        util = PromptServiceBaseTool(platform_key=platform_key)
        index = Index(tool=util, run_id=run_id, capture_metrics=True)
        if VariableReplacementService.is_variables_present(prompt_text=prompt_text):
            prompt_text = VariableReplacementService.replace_variables_in_prompt(
                prompt=output,
                structured_output=structured_output,
                log_events_id=log_events_id,
                tool_id=tool_id,
                prompt_name=prompt_name,
                doc_name=doc_name,
            )

        app.logger.info(f"[{tool_id}] Executing prompt: {prompt_name}")
        publish_log(
            log_events_id,
            {
                "tool_id": tool_id,
                "prompt_key": prompt_name,
                "doc_name": doc_name,
            },
            LogLevel.DEBUG,
            RunLevel.RUN,
            "Executing prompt",
        )

        # Finding and replacing the variables in the prompt
        # The variables are in the form %variable_name%

        output[PSKeys.PROMPTX] = AnswerPromptService.extract_variable(
            structured_output, variable_names, output, prompt_text
        )

        doc_id = index.generate_index_key(
            file_hash=file_hash,
            vector_db=output[PSKeys.VECTOR_DB],
            embedding=output[PSKeys.EMBEDDING],
            x2text=output[PSKeys.X2TEXT_ADAPTER],
            chunk_size=str(output[PSKeys.CHUNK_SIZE]),
            chunk_overlap=str(output[PSKeys.CHUNK_OVERLAP]),
        )
        publish_log(
            log_events_id,
            {
                "tool_id": tool_id,
                "prompt_key": prompt_name,
                "doc_name": doc_name,
            },
            LogLevel.DEBUG,
            RunLevel.RUN,
            "Retrieved document ID",
        )

        try:
            usage_kwargs = {"run_id": run_id, "execution_id": execution_id}
            adapter_instance_id = output[PSKeys.LLM]
            llm = LLM(
                tool=util,
                adapter_instance_id=adapter_instance_id,
                usage_kwargs={
                    **usage_kwargs,
                    PSKeys.LLM_USAGE_REASON: PSKeys.EXTRACTION,
                },
                capture_metrics=True,
            )

            embedding = Embedding(
                tool=util,
                adapter_instance_id=output[PSKeys.EMBEDDING],
                usage_kwargs=usage_kwargs.copy(),
            )

            vector_db = VectorDB(
                tool=util,
                adapter_instance_id=output[PSKeys.VECTOR_DB],
                embedding=embedding,
            )
        except SdkError as e:
            msg = f"Couldn't fetch adapter. {e}"
            app.logger.error(msg)
            publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.ERROR,
                RunLevel.RUN,
                "Unable to obtain LLM / embedding / vectorDB",
            )
            return APIError(message=msg)

        if output[PSKeys.TYPE] == PSKeys.LINE_ITEM:
            try:
                structured_output = AnswerPromptService.extract_line_item(
                    output=output,
                    structured_output=structured_output,
                    llm=llm,
                    enforce_type=output[PSKeys.TYPE],
                    execution_source=execution_source,
                )
                metadata = UsageHelper.query_usage_metadata(
                    token=platform_key, metadata=metadata
                )
                response = {
                    PSKeys.METADATA: metadata,
                    PSKeys.OUTPUT: structured_output,
                    PSKeys.METRICS: metrics,
                }
                return response
            except APIError as api_error:
                app.logger.error(
                    "Failed to extract table for the prompt %s: %s",
                    output[PSKeys.NAME],
                    str(api_error),
                )
                publish_log(
                    log_events_id,
                    {
                        "tool_id": tool_id,
                        "prompt_key": prompt_name,
                        "doc_name": doc_name,
                    },
                    LogLevel.ERROR,
                    RunLevel.TABLE_EXTRACTION,
                    "Error while extracting table for the prompt",
                )
                raise api_error

        try:
            answer = "NA"
            publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.INFO,
                RunLevel.RUN,
                "Retrieving context from adapter",
            )

            retrieval_strategy = output.get(PSKeys.RETRIEVAL_STRATEGY)

            if retrieval_strategy in {PSKeys.SIMPLE, PSKeys.SUBQUESTION}:
                app.logger.info(f"[{tool_id}] Performing retrieval for : {file_path}")
                answer, context = RetrievalService.perform_retrieval(
                    tool_settings=tool_settings,
                    output=output,
                    doc_id=doc_id,
                    llm=llm,
                    vector_db=vector_db,
                    retrieval_type=retrieval_strategy,
                    metadata=metadata,
                    chunk_size=chunk_size,
                    execution_source=execution_source,
                    file_path=file_path,
                    context_retrieval_metrics=context_retrieval_metrics,
                )
                metadata[PSKeys.CONTEXT][output[PSKeys.NAME]] = context
            else:
                app.logger.info(
                    "Invalid retrieval strategy passed: %s",
                    retrieval_strategy,
                )

            publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.DEBUG,
                RunLevel.RUN,
                "Retrieved context from adapter",
            )

            publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.INFO,
                RunLevel.RUN,
                f"Processing prompt type: {output[PSKeys.TYPE]}",
            )

            if output[PSKeys.TYPE] == PSKeys.NUMBER:
                if answer.lower() == "na":
                    structured_output[output[PSKeys.NAME]] = None
                else:
                    # Extract these prompts as constants after pkging
                    prompt = f"Extract the number from the following \
                        text:\n{answer}\n\nOutput just the number. \
                        If the number is expressed in millions \
                        or thousands, expand the number to its numeric value \
                        The number should be directly assignable\
                        to a numeric variable.\
                        It should not have any commas, \
                        percentages or other grouping \
                        characters. No explanation is required.\
                        If you cannot extract the number, output 0."
                    answer = AnswerPromptService.run_completion(
                        llm=llm,
                        prompt=prompt,
                    )
                    try:
                        structured_output[output[PSKeys.NAME]] = float(answer)
                    except Exception as e:
                        app.logger.info(
                            f"Error parsing response (to numeric, float): {e}",
                            LogLevel.ERROR,
                        )
                        structured_output[output[PSKeys.NAME]] = None
                        # No-op adapter always returns a string data and
                        # to keep this response uniform
                        # through all enforce types
                        # we add this check, if not for this,
                        # type casting to float raises
                        # an error and we return None.
                        if isinstance(
                            llm.get_llm(adapter_instance_id=adapter_instance_id),
                            NoOpCustomLLM,
                        ):
                            structured_output[output[PSKeys.NAME]] = answer
            elif output[PSKeys.TYPE] == PSKeys.EMAIL:
                if answer.lower() == "na":
                    structured_output[output[PSKeys.NAME]] = None
                else:
                    prompt = f'Extract the email from the following text:\n{answer}\n\nOutput just the email. \
                        The email should be directly assignable to a string variable. \
                            No explanation is required. If you cannot extract the email, output "NA".'  # noqa
                    answer = AnswerPromptService.run_completion(
                        llm=llm,
                        prompt=prompt,
                    )
                    structured_output[output[PSKeys.NAME]] = answer
            elif output[PSKeys.TYPE] == PSKeys.DATE:
                if answer.lower() == "na":
                    structured_output[output[PSKeys.NAME]] = None
                else:
                    prompt = f'Extract the date from the following text:\n{answer}\n\nOutput just the date.\
                          The date should be in ISO date time format. No explanation is required. \
                            The date should be directly assignable to a date variable. \
                                If you cannot convert the string into a date, output "NA".'  # noqa
                    answer = AnswerPromptService.run_completion(
                        llm=llm,
                        prompt=prompt,
                    )
                    structured_output[output[PSKeys.NAME]] = answer

            elif output[PSKeys.TYPE] == PSKeys.BOOLEAN:
                if answer.lower() == "na":
                    structured_output[output[PSKeys.NAME]] = None
                else:
                    prompt = f'Extract yes/no from the following text:\n{answer}\n\n\
                        Output in single word.\
                        If the context is trying to convey that the answer is true, \
                        then return "yes", else return "no".'
                    answer = AnswerPromptService.run_completion(
                        llm=llm,
                        prompt=prompt,
                    )
                    if answer.lower() == "yes":
                        structured_output[output[PSKeys.NAME]] = True
                    else:
                        structured_output[output[PSKeys.NAME]] = False
            elif output[PSKeys.TYPE] == PSKeys.JSON:
                AnswerPromptService.handle_json(
                    answer=answer,
                    structured_output=structured_output,
                    output=output,
                    log_events_id=log_events_id,
                    tool_id=tool_id,
                    doc_name=doc_name,
                )
            else:
                structured_output[output[PSKeys.NAME]] = answer

            # If there is a trailing '\n' remove it
            if isinstance(structured_output[output[PSKeys.NAME]], str):
                structured_output[output[PSKeys.NAME]] = structured_output[
                    output[PSKeys.NAME]
                ].rstrip("\n")

            # Challenge condition
            if enable_challenge:
                challenge_plugin: dict[str, Any] = PluginManager().get_plugin(
                    PSKeys.CHALLENGE
                )
                try:
                    if challenge_plugin:
                        publish_log(
                            log_events_id,
                            {
                                "tool_id": tool_id,
                                "prompt_key": prompt_name,
                                "doc_name": doc_name,
                            },
                            LogLevel.INFO,
                            RunLevel.CHALLENGE,
                            "Challenging response",
                        )
                        challenge_llm = LLM(
                            tool=util,
                            adapter_instance_id=tool_settings[PSKeys.CHALLENGE_LLM],
                            usage_kwargs={
                                **usage_kwargs,
                                PSKeys.LLM_USAGE_REASON: PSKeys.CHALLENGE,
                            },
                            capture_metrics=True,
                        )
                        challenge = challenge_plugin["entrypoint_cls"](
                            llm=llm,
                            challenge_llm=challenge_llm,
                            run_id=run_id,
                            context="\n".join(context),
                            tool_settings=tool_settings,
                            output=output,
                            structured_output=structured_output,
                            platform_key=platform_key,
                            metadata=metadata,
                        )
                        # Will inline replace the structured output passed.
                        challenge.run()
                    else:
                        app.logger.info(
                            "No challenge plugin found to evaluate prompt: %s",
                            output[PSKeys.NAME],
                        )
                except challenge_plugin["exception_cls"] as e:
                    app.logger.error(
                        "Failed to challenge prompt %s: %s",
                        output[PSKeys.NAME],
                        str(e),
                    )
                    publish_log(
                        log_events_id,
                        {
                            "tool_id": tool_id,
                            "prompt_key": prompt_name,
                            "doc_name": doc_name,
                        },
                        LogLevel.ERROR,
                        RunLevel.CHALLENGE,
                        "Error while challenging response",
                    )

            #
            # Evaluate the prompt.
            #
            if (
                PSKeys.EVAL_SETTINGS in output
                and output[PSKeys.EVAL_SETTINGS][PSKeys.EVAL_SETTINGS_EVALUATE]
            ):
                eval_plugin: dict[str, Any] = PluginManager().get_plugin("evaluation")
                if eval_plugin:
                    publish_log(
                        log_events_id,
                        {
                            "tool_id": tool_id,
                            "prompt_key": prompt_name,
                            "doc_name": doc_name,
                        },
                        LogLevel.INFO,
                        RunLevel.EVAL,
                        "Evaluating response",
                    )
                    try:
                        evaluator = eval_plugin["entrypoint_cls"](
                            "",
                            "".join(context),
                            "",
                            "",
                            output,
                            structured_output,
                            platform_key,
                        )
                        # Will inline replace the structured output passed.
                        evaluator.run()
                    except eval_plugin["exception_cls"] as e:
                        app.logger.error(
                            f"Failed to evaluate prompt {output[PSKeys.NAME]}: {str(e)}"
                        )
                        publish_log(
                            log_events_id,
                            {
                                "tool_id": tool_id,
                                "prompt_key": prompt_name,
                                "doc_name": doc_name,
                            },
                            LogLevel.ERROR,
                            RunLevel.EVAL,
                            "Error while evaluation",
                        )
                    else:
                        publish_log(
                            log_events_id,
                            {
                                "tool_id": tool_id,
                                "prompt_key": prompt_name,
                                "doc_name": doc_name,
                            },
                            LogLevel.DEBUG,
                            RunLevel.EVAL,
                            "Evaluation completed",
                        )
                else:
                    app.logger.info(
                        f"No eval plugin found to evaluate prompt: {output[PSKeys.NAME]}"  # noqa: E501
                    )
        finally:
            challenge_metrics = (
                {f"{challenge_llm.get_usage_reason()}_llm": challenge_llm.get_metrics()}
                if enable_challenge and challenge_llm
                else {}
            )
            metrics.setdefault(prompt_name, {}).update(
                {
                    "context_retrieval": context_retrieval_metrics.get(prompt_name, {}),
                    f"{llm.get_usage_reason()}_llm": llm.get_metrics(),
                    **challenge_metrics,
                }
            )
            vector_db.close()
    publish_log(
        log_events_id,
        {"tool_id": tool_id, "doc_name": doc_name},
        LogLevel.INFO,
        RunLevel.RUN,
        "Sanitizing null values",
    )
    for k, v in structured_output.items():
        if isinstance(v, str) and v.lower() == "na":
            structured_output[k] = None
        elif isinstance(v, list):
            for i in range(len(v)):
                if isinstance(v[i], str) and v[i].lower() == "na":
                    v[i] = None
                elif isinstance(v[i], dict):
                    for k1, v1 in v[i].items():
                        if isinstance(v1, str) and v1.lower() == "na":
                            v[i][k1] = None
        elif isinstance(v, dict):
            for k1, v1 in v.items():
                if isinstance(v1, str) and v1.lower() == "na":
                    v[k1] = None

    publish_log(
        log_events_id,
        {"tool_id": tool_id, "doc_name": doc_name},
        LogLevel.INFO,
        RunLevel.RUN,
        "Execution complete",
    )
    metadata = UsageHelper.query_usage_metadata(token=platform_key, metadata=metadata)
    response = {
        PSKeys.METADATA: metadata,
        PSKeys.OUTPUT: structured_output,
        PSKeys.METRICS: metrics,
    }
    return response
