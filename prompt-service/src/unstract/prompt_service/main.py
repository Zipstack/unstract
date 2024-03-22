import json
import logging
from enum import Enum
from typing import Any, Optional

import peewee
from flask import Flask, request
from llama_index import VectorStoreIndex
from llama_index.llms import LLM
from llama_index.vector_stores.types import ExactMatchFilter, MetadataFilters
from unstract.prompt_service.authentication_middleware import (
    AuthenticationMiddleware,
)
from unstract.prompt_service.constants import PromptServiceContants as PSKeys
from unstract.prompt_service.constants import RunLevel
from unstract.prompt_service.helper import EnvLoader, plugin_loader
from unstract.prompt_service.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.sdk.constants import LogLevel
from unstract.sdk.embedding import ToolEmbedding
from unstract.sdk.index import ToolIndex
from unstract.sdk.llm import ToolLLM
from unstract.sdk.utils.service_context import (
    ServiceContext as UNServiceContext,
)
from unstract.sdk.vector_db import ToolVectorDB

from unstract.core.pubsub_helper import LogPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s : %(message)s",
)

POS_TEXT_PATH = "/tmp/pos.txt"
USE_UNSTRACT_PROMPT = True
MAX_RETRIES = 3

PG_BE_HOST = EnvLoader.get_env_or_die("PG_BE_HOST")
PG_BE_PORT = EnvLoader.get_env_or_die("PG_BE_PORT")
PG_BE_USERNAME = EnvLoader.get_env_or_die("PG_BE_USERNAME")
PG_BE_PASSWORD = EnvLoader.get_env_or_die("PG_BE_PASSWORD")
PG_BE_DATABASE = EnvLoader.get_env_or_die("PG_BE_DATABASE")

be_db = peewee.PostgresqlDatabase(
    PG_BE_DATABASE,
    user=PG_BE_USERNAME,
    password=PG_BE_PASSWORD,
    host=PG_BE_HOST,
    port=PG_BE_PORT,
)
be_db.init(PG_BE_DATABASE)
be_db.connect()

AuthenticationMiddleware.be_db = be_db

app = Flask("prompt-service")

plugins: dict[str, dict[str, Any]] = plugin_loader(app)


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


def construct_prompt(
    preamble: str,
    prompt: str,
    postamble: str,
    grammar_list: list[dict[str, Any]],
    context: str,
) -> str:
    # Let's cleanup the context. Remove if 3 consecutive newlines are found
    context_lines = context.split("\n")
    new_context_lines = []
    empty_line_count = 0
    for line in context_lines:
        if line.strip() == "":
            empty_line_count += 1
        else:
            if empty_line_count >= 3:
                empty_line_count = 3
            for i in range(empty_line_count):
                new_context_lines.append("")
            empty_line_count = 0
            new_context_lines.append(line.rstrip())
    context = "\n".join(new_context_lines)
    app.logger.info(
        f"Old context length: {len(context_lines)}, "
        f"New context length: {len(new_context_lines)}"
    )

    prompt = (
        f"{preamble}\n\nContext:\n---------------{context}\n"
        f"-----------------\n\nQuestion or Instruction: {prompt}\n"
    )
    if grammar_list is not None and len(grammar_list) > 0:
        prompt += "\n"
        for grammar in grammar_list:
            word = ""
            synonyms = []
            if PSKeys.WORD in grammar:
                word = grammar[PSKeys.WORD]
                if PSKeys.SYNONYMS in grammar:
                    synonyms = grammar[PSKeys.SYNONYMS]
            if len(synonyms) > 0 and word != "":
                prompt += f'\nNote: You can consider that the word {word} is same as \
                    {", ".join(synonyms)} in both the quesiton and the context.'  # noqa
    prompt += f"\n\n{postamble}"
    prompt += "\n\nAnswer:"
    return prompt


def construct_prompt_for_engine(
    preamble: str,
    prompt: str,
    postamble: str,
    grammar_list: list[dict[str, Any]],
) -> str:
    # Let's cleanup the context. Remove if 3 consecutive newlines are found
    prompt = f"{preamble}\n\nQuestion or Instruction: {prompt}\n"
    if grammar_list is not None and len(grammar_list) > 0:
        prompt += "\n"
        for grammar in grammar_list:
            word = ""
            synonyms = []
            if PSKeys.WORD in grammar:
                word = grammar[PSKeys.WORD]
                if PSKeys.SYNONYMS in grammar:
                    synonyms = grammar[PSKeys.SYNONYMS]
            if len(synonyms) > 0 and word != "":
                prompt += f'\nNote: You can consider that the word {word} is same as \
                    {", ".join(synonyms)} in both the quesiton and the context.'  # noqa
    prompt += f"\n\n{postamble}"
    prompt += "\n\n"
    return prompt


def authentication_middleware(func: Any) -> Any:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = AuthenticationMiddleware.get_token_from_auth_header(request)
        # Check if bearer token exists and validate it
        if not token or not AuthenticationMiddleware.validate_bearer_token(
            token
        ):
            return "Unauthorized", 401

        return func(*args, **kwargs)

    return wrapper


@app.route(
    "/answer-prompt",
    endpoint="answer_prompt",
    methods=["POST", "GET", "DELETE"],
)
@authentication_middleware
def prompt_processor() -> Any:
    result: dict[str, Any] = {}
    platform_key = AuthenticationMiddleware.get_token_from_auth_header(request)
    if request.method == "POST":
        payload: dict[Any, Any] = request.json
        if not payload:
            result["error"] = "Bad Request / No payload"
            return result, 400
    outputs = payload.get(PSKeys.OUTPUTS)
    tool_id: str = payload.get(PSKeys.TOOL_ID, "")
    file_hash = payload.get(PSKeys.FILE_HASH)
    log_events_id: str = payload.get(PSKeys.LOG_EVENTS_ID, "")

    structured_output: dict[str, Any] = {}
    variable_names: list[str] = []
    _publish_log(
        log_events_id,
        {"tool_id": tool_id},
        LogLevel.DEBUG,
        RunLevel.RUN,
        "Preparing to execute all prompts",
    )

    for output in outputs:  # type:ignore
        variable_names.append(output[PSKeys.NAME])
    for output in outputs:  # type:ignore
        active = output[PSKeys.ACTIVE]
        name = output[PSKeys.NAME]
        promptx = output[PSKeys.PROMPT]
        chunk_size = output[PSKeys.CHUNK_SIZE]
        util = PromptServiceBaseTool(
            log_level=LogLevel.INFO, platform_key=platform_key
        )
        tool_index = ToolIndex(tool=util)

        if active is False:
            app.logger.info(f"[{tool_id}] Skipping inactive prompt: {name}")
            _publish_log(
                log_events_id,
                {"tool_id": tool_id, "prompt_key": name},
                LogLevel.INFO,
                RunLevel.RUN,
                "Skipping inactive prompt",
            )
            continue

        app.logger.info(f"[{tool_id}] Executing prompt: {name}")
        _publish_log(
            log_events_id,
            {"tool_id": tool_id, "prompt_key": name},
            LogLevel.DEBUG,
            RunLevel.RUN,
            "Executing prompt",
        )

        # Finding and replacing the variables in the prompt
        # The variables are in the form %variable_name%

        output[PSKeys.PROMPTX] = extract_variable(
            structured_output, variable_names, output, promptx
        )

        doc_id = ToolIndex.generate_file_id(
            tool_id=tool_id,
            file_hash=file_hash,
            vector_db=output[PSKeys.VECTOR_DB],
            embedding=output[PSKeys.EMBEDDING],
            x2text=output[PSKeys.X2TEXT_ADAPTER],
            chunk_size=output[PSKeys.CHUNK_SIZE],
            chunk_overlap=output[PSKeys.CHUNK_OVERLAP],
        )
        _publish_log(
            log_events_id,
            {"tool_id": tool_id, "prompt_key": name},
            LogLevel.DEBUG,
            RunLevel.RUN,
            "Retrieved document ID",
        )

        llm_helper = ToolLLM(tool=util)
        llm_li: Optional[LLM] = llm_helper.get_llm(
            adapter_instance_id=output[PSKeys.LLM]
        )
        if llm_li is None:
            msg = f"Couldn't fetch LLM {output[PSKeys.LLM]}"
            app.logger.error(msg)
            _publish_log(
                log_events_id,
                {"tool_id": tool_id, "prompt_key": name},
                LogLevel.ERROR,
                RunLevel.RUN,
                "Failed due to LLM error",
            )
            result["error"] = msg
            return result, 500
        embedd_helper = ToolEmbedding(tool=util)
        embedding_li = embedd_helper.get_embedding(
            adapter_instance_id=output[PSKeys.EMBEDDING]
        )
        if embedding_li is None:
            msg = f"Couldn't fetch embedding {output[PSKeys.EMBEDDING]}"
            app.logger.error(msg)
            _publish_log(
                log_events_id,
                {"tool_id": tool_id, "prompt_key": name},
                LogLevel.ERROR,
                RunLevel.RUN,
                "Failed due to embedding error",
            )
            result["error"] = msg
            return result, 500
        embedding_dimension = embedd_helper.get_embedding_length(embedding_li)

        service_context = UNServiceContext.get_service_context(
            platform_api_key=platform_key, llm=llm_li, embed_model=embedding_li
        )
        vdb_helper = ToolVectorDB(
            tool=util,
        )
        vector_db_li = vdb_helper.get_vector_db(
            adapter_instance_id=output[PSKeys.VECTOR_DB],
            embedding_dimension=embedding_dimension,
        )
        if vector_db_li is None:
            msg = f"Couldn't fetch vector DB {output[PSKeys.VECTOR_DB]}"
            app.logger.error(msg)
            result["error"] = msg
            _publish_log(
                log_events_id,
                {"tool_id": tool_id, "prompt_key": name},
                LogLevel.ERROR,
                RunLevel.RUN,
                "Failed due to vector db error",
            )
            return result, 500
        vector_index = VectorStoreIndex.from_vector_store(
            vector_store=vector_db_li, service_context=service_context
        )

        context = ""
        if output[PSKeys.CHUNK_SIZE] == 0:
            # We can do this only for chunkless indexes
            context = tool_index.get_text_from_index(
                embedding_type=output[PSKeys.EMBEDDING],
                vector_db=output[PSKeys.VECTOR_DB],
                doc_id=doc_id,
            )

        assertion_failed = False
        answer = "yes"
        _publish_log(
            log_events_id,
            {"tool_id": tool_id, "prompt_key": name},
            LogLevel.DEBUG,
            RunLevel.RUN,
            "Verifying assertion prompt",
        )

        is_assert = output[PSKeys.IS_ASSERT]
        if is_assert:
            app.logger.debug(f'Asserting prompt: {output["assert_prompt"]}')
            answer = construct_and_run_prompt(
                output,
                llm_helper,
                llm_li,
                context,
                "assert_prompt",
            )
            app.logger.debug(f"Assert response: {answer}")
        if answer.startswith("No") or answer.startswith("no"):
            app.logger.info("Assert failed.")
            _publish_log(
                log_events_id,
                {"tool_id": tool_id, "prompt_key": name},
                LogLevel.DEBUG,
                RunLevel.RUN,
                "Assertion failed",
            )
            assertion_failed = True
            answer = ""
            if (
                output[PSKeys.ASSERTION_FAILURE_PROMPT]
                .lower()
                .startswith("@assign")
            ):
                answer = "NA"
                first_space_index = output[
                    PSKeys.ASSERTION_FAILURE_PROMPT
                ].find(" ")
                if first_space_index > 0:
                    answer = output[PSKeys.ASSERTION_FAILURE_PROMPT][
                        first_space_index + 1
                    ]
                app.logger.info(f"[Assigning] {answer} to the output")
            else:
                answer = construct_and_run_prompt(
                    output,
                    llm_helper,
                    llm_li,
                    context,
                    "assertion_failure_prompt",
                )
        else:
            if chunk_size == 0:
                answer = construct_and_run_prompt(
                    output,
                    llm_helper,
                    llm_li,
                    context,
                    "promptx",
                )
            else:
                answer = "NA"
                _publish_log(
                    log_events_id,
                    {"tool_id": tool_id, "prompt_key": name},
                    LogLevel.INFO,
                    RunLevel.RUN,
                    "Retrieving context from adapter",
                )

                if output[PSKeys.RETRIEVAL_STRATEGY] == PSKeys.SIMPLE:
                    answer, context = simple_retriver(
                        output,
                        doc_id,
                        llm_helper,
                        llm_li,
                        vector_index,
                    )
                else:
                    app.logger.info(
                        "Invalid retrieval strategy "
                        f"passed {output[PSKeys.RETRIEVAL_STRATEGY]}"
                    )

                _publish_log(
                    log_events_id,
                    {"tool_id": tool_id, "prompt_key": name},
                    LogLevel.DEBUG,
                    RunLevel.RUN,
                    "Retrieved context from adapter",
                )

        _publish_log(
            log_events_id,
            {"tool_id": tool_id, "prompt_key": name},
            LogLevel.INFO,
            RunLevel.RUN,
            f"Processing prompt type: {output[PSKeys.TYPE]}",
        )

        if output[PSKeys.TYPE] == PSKeys.NUMBER:
            if assertion_failed or answer.lower() == "na":
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
                    llm_helper,
                    llm_li,
                    prompt,
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
            if assertion_failed or answer.lower() == "na":
                structured_output[output[PSKeys.NAME]] = None
            else:
                prompt = f'Extract the email from the following text:\n{answer}\n\nOutput just the email. \
                    The email should be directly assignable to a string variable. \
                        No explanation is required. If you cannot extract the email, output "NA".'  # noqa
                answer = run_completion(
                    llm_helper,
                    llm_li,
                    prompt,
                )
                structured_output[output[PSKeys.NAME]] = answer
        elif output[PSKeys.TYPE] == PSKeys.DATE:
            if assertion_failed or answer.lower() == "na":
                structured_output[output[PSKeys.NAME]] = None
            else:
                prompt = f'Extract the date from the following text:\n{answer}\n\nOutput just the date.\
                      The date should be in ISO date time format. No explanation is required. \
                        The date should be directly assignable to a date variable. \
                            If you cannot convert the string into a date, output "NA".'  # noqa
                answer = run_completion(
                    llm_helper,
                    llm_li,
                    prompt,
                )
                structured_output[output[PSKeys.NAME]] = answer

        elif output[PSKeys.TYPE] == PSKeys.BOOLEAN:
            if assertion_failed or answer.lower() == "na":
                structured_output[output[PSKeys.NAME]] = None
            else:
                if answer.lower() == "yes":
                    structured_output[output[PSKeys.NAME]] = True
                else:
                    structured_output[output[PSKeys.NAME]] = False
        elif output[PSKeys.TYPE] == PSKeys.JSON:
            if (
                assertion_failed
                or answer.lower() == "[]"
                or answer.lower() == "na"
            ):
                structured_output[output[PSKeys.NAME]] = None
            else:
                # Remove any markdown code blocks
                lines = answer.split("\n")
                answer = ""
                for line in lines:
                    if line.strip().startswith("```"):
                        continue
                    answer += line + "\n"
                try:
                    structured_output[output[PSKeys.NAME]] = json.loads(answer)
                except Exception as e:
                    app.logger.info(
                        f"JSON format error : {answer}", LogLevel.ERROR
                    )
                    app.logger.info(
                        f"Error parsing response (to json): {e}", LogLevel.ERROR
                    )
                    structured_output[output[PSKeys.NAME]] = []
        else:
            structured_output[output[PSKeys.NAME]] = answer

        # If there is a trailing '\n' remove it
        if isinstance(structured_output[output[PSKeys.NAME]], str):
            structured_output[output[PSKeys.NAME]] = structured_output[
                output[PSKeys.NAME]
            ].rstrip("\n")

        # Challenge condition
        if "enable_challenge" in output and output["enable_challenge"]:
            challenge_plugin: dict[str, Any] = plugins.get("challenge", {})
            try:
                if challenge_plugin:
                    tool_settings: dict[str, Any] = {
                        PSKeys.PREAMBLE: output[PSKeys.PREAMBLE],
                        PSKeys.POSTAMBLE: output[PSKeys.POSTAMBLE],
                        PSKeys.GRAMMAR: output[PSKeys.GRAMMAR],
                        PSKeys.LLM: output[PSKeys.LLM],
                        PSKeys.CHALLENGE_LLM: output[PSKeys.CHALLENGE_LLM],
                    }
                    challenge = challenge_plugin["entrypoint_cls"](
                        llm_helper=llm_helper,
                        context=context,
                        tool_settings=tool_settings,
                        output=output,
                        structured_output=structured_output,
                        logger=app.logger,
                        platform_key=platform_key,
                    )
                    # Will inline replace the structured output passed.
                    challenge.run()
                else:
                    app.logger.info(
                        "No challenge plugin found to evaluate prompt: %s",
                        output["name"],
                    )
            except challenge_plugin["exception_cls"] as e:
                app.logger.error(
                    "Failed to challenge prompt %s: %s", output["name"], str(e)
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
                    {"tool_id": tool_id, "prompt_key": name},
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
                        f'Failed to evaluate prompt {output["name"]}: {str(e)}'
                    )
                    _publish_log(
                        log_events_id,
                        {"tool_id": tool_id, "prompt_key": name},
                        LogLevel.ERROR,
                        RunLevel.EVAL,
                        "Error while evaluation",
                    )
                else:
                    _publish_log(
                        log_events_id,
                        {"tool_id": tool_id, "prompt_key": name},
                        LogLevel.DEBUG,
                        RunLevel.EVAL,
                        "Evaluation completed",
                    )
            else:
                app.logger.info(
                    f'No eval plugin found to evaluate prompt: {output["name"]}'  # noqa: E501
                )

    _publish_log(
        log_events_id,
        {"tool_id": tool_id},
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
        {"tool_id": tool_id},
        LogLevel.INFO,
        RunLevel.RUN,
        "Execution complete",
    )
    return structured_output


def simple_retriver(  # type:ignore
    output: dict[str, Any],
    doc_id: str,
    llm_helper: ToolLLM,
    llm_li: Optional[LLM],
    vector_index,
) -> tuple[str, str]:
    prompt = construct_prompt_for_engine(
        preamble=output["preamble"],
        prompt=output["promptx"],
        postamble=output["postamble"],
        grammar_list=output["grammar"],
    )
    subq_prompt = (
        f"Generate a sub-question from the following verbose prompt that will"
        f" help extract relevant documents from a vector store:\n\n{prompt}"
    )
    answer: str = run_completion(
        llm_helper,
        llm_li,
        subq_prompt,
    )

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
        if node.score > 0.6:
            text += node.get_content() + "\n"
        else:
            app.logger.info(
                "Node score is less than 0.6. " f"Ignored: {node.score}"
            )

    answer: str = construct_and_run_prompt(  # type:ignore
        output,
        llm_helper,
        llm_li,
        text,
        "promptx",
    )
    return (answer, text)


def construct_and_run_prompt(
    output: dict[str, Any],
    llm_helper: ToolLLM,
    llm_li: Optional[LLM],
    context: str,
    prompt: str,
) -> str:
    prompt = construct_prompt(
        preamble=output[PSKeys.PREAMBLE],
        prompt=output[prompt],
        postamble=output[PSKeys.POSTAMBLE],
        grammar_list=output[PSKeys.GRAMMAR],
        context=context,
    )
    try:
        answer: str = run_completion(
            llm_helper,
            llm_li,
            prompt,
        )
        return answer
    except Exception as e:
        app.logger.info(f"Error completing prompt: {e}.")
        raise e


def run_completion(
    llm_helper: ToolLLM,
    llm_li: Optional[LLM],
    prompt: str,
) -> str:
    try:
        platform_api_key = llm_helper.tool.get_env_or_die(
            PSKeys.PLATFORM_SERVICE_API_KEY
        )
        completion = llm_helper.run_completion(
            llm_li, platform_api_key, prompt, 3
        )

        answer: str = completion[PSKeys.RESPONSE].text
        return answer
    except Exception as e:
        app.logger.info(f"Error completing prompt: {e}.")
        raise e


def extract_variable(
    structured_output: dict[str, Any],
    variable_names: list[Any],
    output: dict[str, Any],
    promptx: str,
) -> str:
    for variable_name in variable_names:
        if promptx.find(f"%{variable_name}%") >= 0:
            if variable_name in structured_output:
                promptx = promptx.replace(
                    f"%{variable_name}%",
                    str(structured_output[variable_name]),
                )
            else:
                raise ValueError(
                    f"Variable {variable_name} not found "
                    "in structured output"
                )

    if promptx != output[PSKeys.PROMPT]:
        app.logger.info(f"Prompt after variable replacement: {promptx}")
    return promptx


def enable_single_pass_extraction() -> None:
    """Enables single-pass-extraction plugin if available."""
    single_pass_extration_plugin: dict[str, Any] = plugins.get(
        "single-pass-extraction", {}
    )
    if single_pass_extration_plugin:
        single_pass_extration_plugin["entrypoint_cls"](
            app=app, challenge_plugin=plugins.get("challenge", {})
        )


enable_single_pass_extraction()


if __name__ == "__main__":
    # Start the server
    app.run(host="0.0.0.0", port=5003)
