import time
import traceback
from enum import Enum
from json import JSONDecodeError
from typing import Any, Optional

from flask import json, jsonify, request
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from unstract.prompt_service.authentication_middleware import AuthenticationMiddleware
from unstract.prompt_service.config import create_app, db
from unstract.prompt_service.constants import PromptServiceContants as PSKeys
from unstract.prompt_service.constants import RunLevel
from unstract.prompt_service.exceptions import APIError, ErrorResponse, NoPayloadError
from unstract.prompt_service.helper import (
    construct_and_run_prompt,
    extract_table,
    extract_variable,
    get_cleaned_context,
    plugin_loader,
    plugins,
    query_usage_metadata,
    run_completion,
)
from unstract.prompt_service.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.prompt_service.variable_extractor.base import VariableExtractor
from unstract.sdk.constants import LogLevel
from unstract.sdk.embedding import Embedding
from unstract.sdk.exceptions import SdkError
from unstract.sdk.index import Index
from unstract.sdk.llm import LLM
from unstract.sdk.vector_db import VectorDB
from werkzeug.exceptions import HTTPException

from unstract.core.pubsub_helper import LogPublisher

USE_UNSTRACT_PROMPT = True
MAX_RETRIES = 3

NO_CONTEXT_ERROR = (
    "Couldn't fetch context from vector DB. "
    "This happens usually due to a delay by the Vector DB "
    "provider to confirm writes to db. "
    "Please try again after some time"
)

app = create_app()
# Load plugins
plugin_loader(app)


@app.before_request
def before_request() -> None:
    if db.is_closed():
        db.connect(reuse_if_open=True)


@app.teardown_request
def after_request(exception: Any) -> None:
    # Close the connection after each request
    if not db.is_closed():
        db.close()


@app.before_request
def log_request_info():
    app.logger.info(f"Request Path: {request.path} | Method: {request.method}")


@app.after_request
def log_response_info(response):
    app.logger.info(f"Response Status: {response.status}")
    return response


def _publish_log(
    log_events_id: str,
    component: dict[str, str],
    level: Enum,
    state: Enum,
    message: str,
) -> None:
    LogPublisher.publish(
        log_events_id,
        LogPublisher.log_prompt(component, level.value, state.value, message),
    )


def authentication_middleware(func: Any) -> Any:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = AuthenticationMiddleware.get_token_from_auth_header(request)
        # Check if bearer token exists and validate it
        if not token or not AuthenticationMiddleware.validate_bearer_token(token):
            return "Unauthorized", 401

        return func(*args, **kwargs)

    return wrapper


@app.route(
    "/answer-prompt",
    endpoint="answer_prompt",
    methods=["POST"],
)
@authentication_middleware
def prompt_processor() -> Any:
    platform_key = AuthenticationMiddleware.get_token_from_auth_header(request)
    payload: dict[Any, Any] = request.json
    if not payload:
        raise NoPayloadError
    tool_settings = payload.get(PSKeys.TOOL_SETTINGS, {})
    outputs = payload.get(PSKeys.OUTPUTS, [])
    tool_id: str = payload.get(PSKeys.TOOL_ID, "")
    run_id: str = payload.get(PSKeys.RUN_ID, "")
    file_hash = payload.get(PSKeys.FILE_HASH)
    doc_name = str(payload.get(PSKeys.FILE_NAME, ""))
    log_events_id: str = payload.get(PSKeys.LOG_EVENTS_ID, "")
    structured_output: dict[str, Any] = {}
    metadata: dict[str, Any] = {
        PSKeys.RUN_ID: run_id,
        PSKeys.FILE_NAME: doc_name,
        PSKeys.CONTEXT: {},
    }
    variable_names: list[str] = []
    _publish_log(
        log_events_id,
        {"tool_id": tool_id, "run_id": run_id, "doc_name": doc_name},
        LogLevel.DEBUG,
        RunLevel.RUN,
        f"Preparing to execute {len(outputs)} prompt(s)",
    )

    for output in outputs:  # type:ignore
        variable_names.append(output[PSKeys.NAME])
    for output in outputs:  # type:ignore
        prompt_name = output[PSKeys.NAME]
        promptx = output[PSKeys.PROMPT]
        chunk_size = output[PSKeys.CHUNK_SIZE]
        util = PromptServiceBaseTool(log_level=LogLevel.INFO, platform_key=platform_key)
        index = Index(tool=util)

        app.logger.info(f"[{tool_id}] Replacing variables in prompt : {prompt_name}")
        _publish_log(
            log_events_id,
            {
                "tool_id": tool_id,
                "prompt_key": prompt_name,
                "doc_name": doc_name,
            },
            LogLevel.DEBUG,
            RunLevel.RUN,
            "Replacing variables in prompt",
        )
        try:
            variable_map = output[PSKeys.VARIABLE_MAP]
            promptx = VariableExtractor.execute_variable_replacement(
                prompt=promptx, variable_map=variable_map
            )
            app.logger.info(f"[{tool_id}] Prompt after variable replacement: {promptx}")
            _publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.DEBUG,
                RunLevel.RUN,
                f"Prompt after variable replacement:{promptx} ",
            )
        except KeyError:
            # Executed incase of structured tool and
            # APIs where we do not set the variable map
            promptx = VariableExtractor.execute_variable_replacement(
                prompt=promptx, variable_map=structured_output
            )
            app.logger.info(f"[{tool_id}] Prompt after variable replacement: {promptx}")
            _publish_log(
                log_events_id,
                {
                    "tool_id": tool_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevel.DEBUG,
                RunLevel.RUN,
                f"Prompt after variable replacement:{promptx} ",
            )
        except APIError as api_error:
            raise api_error

        app.logger.info(f"[{tool_id}] Executing prompt: {prompt_name}")
        _publish_log(
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

        output[PSKeys.PROMPTX] = extract_variable(
            structured_output, variable_names, output, promptx
        )

        doc_id = index.generate_index_key(
            file_hash=file_hash,
            vector_db=output[PSKeys.VECTOR_DB],
            embedding=output[PSKeys.EMBEDDING],
            x2text=output[PSKeys.X2TEXT_ADAPTER],
            chunk_size=str(output[PSKeys.CHUNK_SIZE]),
            chunk_overlap=str(output[PSKeys.CHUNK_OVERLAP]),
        )
        _publish_log(
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
            usage_kwargs = {"run_id": run_id}
            adapter_instance_id = output[PSKeys.LLM]
            llm = LLM(
                tool=util,
                adapter_instance_id=adapter_instance_id,
                usage_kwargs={
                    **usage_kwargs,
                    PSKeys.LLM_USAGE_REASON: PSKeys.EXTRACTION,
                },
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
            _publish_log(
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

        if output[PSKeys.TYPE] == PSKeys.TABLE:
            try:
                structured_output = extract_table(
                    output=output,
                    plugins=plugins,
                    structured_output=structured_output,
                    llm=llm,
                )
                metadata = query_usage_metadata(token=platform_key, metadata=metadata)
                response = {
                    PSKeys.METADATA: metadata,
                    PSKeys.OUTPUT: structured_output,
                }
                return response
            except APIError as api_error:
                app.logger.error(
                    "Failed to extract table for the prompt %s: %s",
                    output[PSKeys.NAME],
                    str(api_error),
                )
                _publish_log(
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

        try:
            context = ""
            if output[PSKeys.CHUNK_SIZE] == 0:
                # We can do this only for chunkless indexes
                context: Optional[str] = index.query_index(
                    embedding_instance_id=output[PSKeys.EMBEDDING],
                    vector_db_instance_id=output[PSKeys.VECTOR_DB],
                    doc_id=doc_id,
                    usage_kwargs=usage_kwargs,
                )
                if not context:
                    # UN-1288 For Pinecone, we are seeing an inconsistent case where
                    # query with doc_id fails even though indexing just happened.
                    # This causes the following retrieve to return no text.
                    # To rule out any lag on the Pinecone vector DB write,
                    # the following sleep is added.
                    # Note: This will not fix the issue. Since this issue is
                    # inconsistent, and not reproducible easily,
                    # this is just a safety net.
                    time.sleep(2)
                    context: Optional[str] = index.query_index(
                        embedding_instance_id=output[PSKeys.EMBEDDING],
                        vector_db_instance_id=output[PSKeys.VECTOR_DB],
                        doc_id=doc_id,
                        usage_kwargs=usage_kwargs,
                    )
                    if context is None:
                        # TODO: Obtain user set name for vector DB
                        msg = NO_CONTEXT_ERROR
                        app.logger.error(
                            f"{msg} {output[PSKeys.VECTOR_DB]} for doc_id {doc_id}"
                        )
                        _publish_log(
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
                # TODO: Use vectorDB name when available
                _publish_log(
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

            if chunk_size == 0:
                _publish_log(
                    log_events_id,
                    {
                        "tool_id": tool_id,
                        "prompt_key": prompt_name,
                        "doc_name": doc_name,
                    },
                    LogLevel.INFO,
                    RunLevel.RUN,
                    "Retrieving answer from LLM",
                )
                answer = construct_and_run_prompt(
                    tool_settings=tool_settings,
                    output=output,
                    llm=llm,
                    context=context,
                    prompt="promptx",
                    metadata=metadata,
                )
                metadata[PSKeys.CONTEXT][output[PSKeys.NAME]] = get_cleaned_context(
                    context
                )
            else:
                answer = "NA"
                _publish_log(
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
                    vector_index = vector_db.get_vector_store_index()
                    answer, context = run_retrieval(
                        tool_settings=tool_settings,
                        output=output,
                        doc_id=doc_id,
                        llm=llm,
                        vector_index=vector_index,
                        retrieval_type=retrieval_strategy,
                        metadata=metadata,
                    )
                    metadata[PSKeys.CONTEXT][output[PSKeys.NAME]] = get_cleaned_context(
                        context
                    )
                else:
                    app.logger.info(
                        "Invalid retrieval strategy passed: %s",
                        retrieval_strategy,
                    )

                _publish_log(
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

            _publish_log(
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
                    # TODO: Extract these prompts as constants after pkging
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
                    answer = run_completion(
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
            elif output[PSKeys.TYPE] == PSKeys.EMAIL:
                if answer.lower() == "na":
                    structured_output[output[PSKeys.NAME]] = None
                else:
                    prompt = f'Extract the email from the following text:\n{answer}\n\nOutput just the email. \
                        The email should be directly assignable to a string variable. \
                            No explanation is required. If you cannot extract the email, output "NA".'  # noqa
                    answer = run_completion(
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
                    answer = run_completion(
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
                    answer = run_completion(
                        llm=llm,
                        prompt=prompt,
                    )
                    if answer.lower() == "yes":
                        structured_output[output[PSKeys.NAME]] = True
                    else:
                        structured_output[output[PSKeys.NAME]] = False
            elif output[PSKeys.TYPE] == PSKeys.JSON:
                if answer.lower() == "[]" or answer.lower() == "na":
                    structured_output[output[PSKeys.NAME]] = None
                else:
                    try:
                        structured_output[output[PSKeys.NAME]] = json.loads(answer)
                    except JSONDecodeError:
                        prompt = f"Convert the following text into valid JSON string: \
                            \n{answer}\n\n The JSON string should be able to be parsed \
                            into a Python dictionary. \
                            Output just the JSON string. No explanation is required. \
                            If you cannot extract the JSON string, output {{}}"
                        try:
                            answer = run_completion(
                                llm=llm,
                                prompt=prompt,
                                prompt_type=PSKeys.JSON,
                            )
                            structured_output[output[PSKeys.NAME]] = json.loads(answer)
                        except JSONDecodeError as e:
                            app.logger.info(
                                f"JSON format error : {answer}", LogLevel.ERROR
                            )
                            app.logger.info(
                                f"Error parsing response (to json): {e}",
                                LogLevel.ERROR,
                            )
                            structured_output[output[PSKeys.NAME]] = {}

            else:
                structured_output[output[PSKeys.NAME]] = answer

            # If there is a trailing '\n' remove it
            if isinstance(structured_output[output[PSKeys.NAME]], str):
                structured_output[output[PSKeys.NAME]] = structured_output[
                    output[PSKeys.NAME]
                ].rstrip("\n")

            enable_challenge = tool_settings.get(PSKeys.ENABLE_CHALLENGE)
            # Challenge condition
            if enable_challenge:
                challenge_plugin: dict[str, Any] = plugins.get(PSKeys.CHALLENGE, {})
                try:
                    if challenge_plugin:
                        _publish_log(
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
                        )
                        challenge = challenge_plugin["entrypoint_cls"](
                            llm=llm,
                            challenge_llm=challenge_llm,
                            run_id=run_id,
                            context=context,
                            tool_settings=tool_settings,
                            output=output,
                            structured_output=structured_output,
                            logger=app.logger,
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
                    _publish_log(
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
                eval_plugin: dict[str, Any] = plugins.get("evaluation", {})
                if eval_plugin:
                    _publish_log(
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
                            context,
                            "",
                            "",
                            output,
                            structured_output,
                            app.logger,
                            platform_key,
                        )
                        # Will inline replace the structured output passed.
                        evaluator.run()
                    except eval_plugin["exception_cls"] as e:
                        app.logger.error(
                            f"Failed to evaluate prompt {output[PSKeys.NAME]}: {str(e)}"
                        )
                        _publish_log(
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
                        _publish_log(
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
            vector_db.close()
    _publish_log(
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

    _publish_log(
        log_events_id,
        {"tool_id": tool_id, "doc_name": doc_name},
        LogLevel.INFO,
        RunLevel.RUN,
        "Execution complete",
    )
    metadata = query_usage_metadata(token=platform_key, metadata=metadata)
    response = {PSKeys.METADATA: metadata, PSKeys.OUTPUT: structured_output}
    return response


def run_retrieval(  # type:ignore
    tool_settings: dict[str, Any],
    output: dict[str, Any],
    doc_id: str,
    llm: LLM,
    vector_index,
    retrieval_type: str,
    metadata: dict[str, Any],
) -> tuple[str, str]:
    context: str = ""
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
            " that each subquestion targets a distinct aspect of the original query."
            " Please note that, there are cases where the "
            "response might have a list of answers. The subquestions must not miss out "
            "any values in these cases. "
            "Output should be a list of comma seperated "
            "subquestion prompts. Do not change this format. \n \n "
            " Subquestions : "
        )
        subquestions = run_completion(
            llm=llm,
            prompt=subq_prompt,
        )
        subquestion_list = subquestions.split(",")
        raw_retrieved_context = ""
        for each_subq in subquestion_list:
            retrieved_context = _retrieve_context(
                output, doc_id, vector_index, each_subq
            )
            # Not adding the potential for pinecode serverless
            # inconsistency issue owing to risk of infinte loop
            # and inablity to diffrentiate genuine cases of
            # empty context.
            raw_retrieved_context = "\f\n".join(
                [raw_retrieved_context, retrieved_context]
            )
        context = _remove_duplicate_nodes(raw_retrieved_context)

    if retrieval_type == PSKeys.SIMPLE:

        context = _retrieve_context(output, doc_id, vector_index, prompt)

        if not context:
            # UN-1288 For Pinecone, we are seeing an inconsistent case where
            # query with doc_id fails even though indexing just happened.
            # This causes the following retrieve to return no text.
            # To rule out any lag on the Pinecone vector DB write,
            # the following sleep is added
            # Note: This will not fix the issue. Since this issue is inconsistent
            # and not reproducible easily, this is just a safety net.
            time.sleep(2)
            context = _retrieve_context(output, doc_id, vector_index, prompt)

    answer = construct_and_run_prompt(  # type:ignore
        tool_settings=tool_settings,
        output=output,
        llm=llm,
        context=context,
        prompt="promptx",
        metadata=metadata,
    )

    return (answer, context)


def _remove_duplicate_nodes(retrieved_context: str) -> str:
    context_set: set[str] = set(retrieved_context.split("\f\n"))
    fomatted_context = "\f\n".join(context_set)
    return fomatted_context


def _retrieve_context(output, doc_id, vector_index, answer) -> str:
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
    text = ""
    for node in nodes:
        # ToDo: May have to fine-tune this value for node score or keep it
        # configurable at the adapter level
        if node.score > 0:
            text += node.get_content() + "\f\n"
        else:
            app.logger.info("Node score is less than 0. " f"Ignored: {node.score}")
    return text


def log_exceptions(e: HTTPException):
    """Helper method to log exceptions.

    Args:
        e (HTTPException): Exception to log
    """
    code = 500
    if hasattr(e, "code"):
        code = e.code or code

    if code >= 500:
        message = "{method} {url} {status}\n\n{error}\n\n````{tb}````".format(
            method=request.method,
            url=request.url,
            status=code,
            error=str(e),
            tb=traceback.format_exc(),
        )
    else:
        message = "{method} {url} {status} {error}".format(
            method=request.method,
            url=request.url,
            status=code,
            error=str(e),
        )
    app.logger.error(message)


@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException):
    """Return JSON instead of HTML for HTTP errors."""
    log_exceptions(e)
    if isinstance(e, APIError):
        return jsonify(e.to_dict()), e.code
    else:
        response = e.get_response()
        response.data = json.dumps(
            ErrorResponse(error=e.description, name=e.name, code=e.code)
        )
        response.content_type = "application/json"
        return response


@app.errorhandler(Exception)
def handle_uncaught_exception(e):
    """Handler for uncaught exceptions.

    Args:
        e (Exception): Any uncaught exception
    """
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return handle_http_exception(e)

    log_exceptions(e)
    return handle_http_exception(APIError())


# TODO: Review if below code is needed
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
