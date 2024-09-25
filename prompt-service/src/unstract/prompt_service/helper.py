import importlib
import os
from json import JSONDecodeError
from logging import Logger
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from flask import Flask, current_app, json
from unstract.prompt_service.authentication_middleware import AuthenticationMiddleware
from unstract.prompt_service.config import db
from unstract.prompt_service.constants import PromptServiceContants as PSKeys
from unstract.prompt_service.exceptions import APIError, RateLimitError
from unstract.sdk.exceptions import RateLimitError as SdkRateLimitError
from unstract.sdk.exceptions import SdkError
from unstract.sdk.llm import LLM

load_dotenv()

# Global variable to store plugins
plugins: dict[str, dict[str, Any]] = {}


def plugin_loader(app: Flask) -> None:
    """Loads plugins found in the plugins root dir.

    Each plugin:
    * needs to be a package dir AND
    * should contain a src/__init__.py which exports below:

        metadata: dict[str, Any] = {
            "version": str,
            "name": str,
            "entrypoint_cls": class,
            "exception_cls": class,
            "disable": bool
        }
    """
    global plugins
    plugins_dir: Path = Path(os.path.dirname(__file__)) / "plugins"
    plugins_pkg = "unstract.prompt_service.plugins"

    if not plugins_dir.exists():
        app.logger.info(f"Plugins dir not found: {plugins_dir}. Skipping.")
        return

    app.logger.info(f"Loading plugins from: {plugins_dir}")

    for pkg in os.listdir(os.fspath(plugins_dir)):
        if pkg.endswith(".so"):
            pkg = pkg.split(".")[0]
        pkg_anchor = f"{plugins_pkg}.{pkg}.src"
        try:
            module = importlib.import_module(pkg_anchor)
        except ImportError as e:
            app.logger.error(f"Failed to load plugin ({pkg}): {str(e)}")
            continue

        if not hasattr(module, "metadata"):
            app.logger.warn(f"Plugin metadata not found: {pkg}")
            continue

        metadata: dict[str, Any] = module.metadata
        if metadata.get("disable", False):
            app.logger.info(f"Ignore disabled plugin: {pkg} v{metadata['version']}")
            continue

        try:
            plugins[metadata["name"]] = {
                "version": metadata["version"],
                "entrypoint_cls": metadata["entrypoint_cls"],
                "exception_cls": metadata["exception_cls"],
            }
            app.logger.info(f"Loaded plugin: {pkg} v{metadata['version']}")
        except KeyError as e:
            app.logger.error(f"Invalid metadata for plugin '{pkg}': {str(e)}")

    if not plugins:
        app.logger.info("No plugins found.")

    initialize_plugin_endpoints(app=app)


def get_cleaned_context(context: str) -> str:
    clean_context_plugin: dict[str, Any] = plugins.get(PSKeys.CLEAN_CONTEXT, {})
    if clean_context_plugin:
        return clean_context_plugin["entrypoint_cls"].run(context=context)
    return context


def initialize_plugin_endpoints(app: Flask) -> None:
    """Enables plugins if available."""
    single_pass_extration_plugin: dict[str, Any] = plugins.get(
        PSKeys.SINGLE_PASS_EXTRACTION, {}
    )
    summarize_plugin: dict[str, Any] = plugins.get(PSKeys.SUMMARIZE, {})
    simple_prompt_studio: dict[str, Any] = plugins.get(PSKeys.SIMPLE_PROMPT_STUDIO, {})
    if single_pass_extration_plugin:
        single_pass_extration_plugin["entrypoint_cls"](
            app=app,
            challenge_plugin=plugins.get(PSKeys.CHALLENGE, {}),
            get_cleaned_context=get_cleaned_context,
        )
    if summarize_plugin:
        summarize_plugin["entrypoint_cls"](
            app=app,
        )
    if simple_prompt_studio:
        simple_prompt_studio["entrypoint_cls"](
            app=app,
        )


def query_usage_metadata(token: str, metadata: dict[str, Any]) -> dict[str, Any]:
    org_id: str = AuthenticationMiddleware.get_account_from_bearer_token(token)
    run_id: str = metadata["run_id"]
    query: str = f"""
        SELECT
            usage_type,
            llm_usage_reason,
            model_name,
            SUM(prompt_tokens) AS input_tokens,
            SUM(completion_tokens) AS output_tokens,
            SUM(total_tokens) AS total_tokens,
            SUM(embedding_tokens) AS embedding_tokens,
            SUM(cost_in_dollars) AS cost_in_dollars
        FROM "{org_id}"."token_usage"
        WHERE run_id = %s
        GROUP BY usage_type, llm_usage_reason, model_name;
    """
    logger: Logger = current_app.logger
    try:
        with db.atomic():
            logger.info(
                "Querying usage metadata for org_id: %s, run_id: %s", org_id, run_id
            )
            cursor = db.execute_sql(query, (run_id,))
            results: list[tuple] = cursor.fetchall()
            # Process results as needed
            for row in results:
                key, item = _get_key_and_item(row)
                # Initialize the key as an empty list if it doesn't exist
                if key not in metadata:
                    metadata[key] = []
                # Append the item to the list associated with the key
                metadata[key].append(item)
    except Exception as e:
        logger.error(f"Error executing querying usage metadata: {e}")
    return metadata


def _get_key_and_item(row: tuple) -> tuple[str, dict[str, Any]]:
    (
        usage_type,
        llm_usage_reason,
        model_name,
        input_tokens,
        output_tokens,
        total_tokens,
        embedding_tokens,
        cost_in_dollars,
    ) = row
    cost_in_dollars: str = _format_float_positional(cost_in_dollars)
    key: str = usage_type
    item: dict[str, Any] = {
        "model_name": model_name,
        "cost_in_dollars": cost_in_dollars,
    }
    if llm_usage_reason:
        key = f"{llm_usage_reason}_{key}"
        item["input_tokens"] = input_tokens
        item["output_tokens"] = output_tokens
        item["total_tokens"] = total_tokens
    else:
        item["embedding_tokens"] = embedding_tokens
    return key, item


def _format_float_positional(value: float, precision: int = 10) -> str:
    formatted: str = f"{value:.{precision}f}"
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def extract_variable(
    structured_output: dict[str, Any],
    variable_names: list[Any],
    output: dict[str, Any],
    promptx: str,
) -> str:
    logger: Logger = current_app.logger
    for variable_name in variable_names:
        if promptx.find(f"%{variable_name}%") >= 0:
            if variable_name in structured_output:
                promptx = promptx.replace(
                    f"%{variable_name}%",
                    str(structured_output[variable_name]),
                )
            else:
                raise ValueError(
                    f"Variable {variable_name} not found " "in structured output"
                )

    if promptx != output[PSKeys.PROMPT]:
        logger.info(f"Prompt after variable replacement: {promptx}")
    return promptx


def construct_and_run_prompt(
    tool_settings: dict[str, Any],
    output: dict[str, Any],
    llm: LLM,
    context: str,
    prompt: str,
    metadata: dict[str, Any],
) -> str:
    platform_postamble = tool_settings.get(PSKeys.PLATFORM_POSTAMBLE, "")
    if tool_settings.get(PSKeys.SUMMARIZE_AS_SOURCE):
        platform_postamble = ""
    prompt = construct_prompt(
        preamble=tool_settings.get(PSKeys.PREAMBLE, ""),
        prompt=output[prompt],
        postamble=tool_settings.get(PSKeys.POSTAMBLE, ""),
        grammar_list=tool_settings.get(PSKeys.GRAMMAR, []),
        context=context,
        platform_postamble=platform_postamble,
    )
    return run_completion(
        llm=llm,
        prompt=prompt,
        metadata=metadata,
        prompt_key=output[PSKeys.NAME],
    )


def construct_prompt(
    preamble: str,
    prompt: str,
    postamble: str,
    grammar_list: list[dict[str, Any]],
    context: str,
    platform_postamble: str,
) -> str:
    prompt = (
        f"{preamble}\n\nContext:\n---------------\n{context}\n"
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
    if platform_postamble:
        platform_postamble += "\n\n"
    prompt += f"\n\n{postamble}\n\n{platform_postamble}Answer:"
    return prompt


def run_completion(
    llm: LLM,
    prompt: str,
    metadata: Optional[dict[str, str]] = None,
    prompt_key: Optional[str] = None,
) -> str:
    logger: Logger = current_app.logger
    try:
        extract_epilogue_plugin: dict[str, Any] = plugins.get(
            PSKeys.EXTRACT_EPILOGUE, {}
        )
        extract_epilogue = None
        if extract_epilogue_plugin:
            extract_epilogue = extract_epilogue_plugin["entrypoint_cls"].run
        completion = llm.complete(
            prompt=prompt,
            process_text=extract_epilogue,
        )
        answer: str = completion[PSKeys.RESPONSE].text
        epilogue = completion.get(PSKeys.EPILOGUE)
        if all([metadata, epilogue, prompt_key]):
            try:
                logger.info(f"Epilogue extracted from LLM: {epilogue}")
                epilogue = json.loads(epilogue)
            except JSONDecodeError:
                logger.error(f"Failed to convert epilogue to JSON: {epilogue}")
            metadata.setdefault(PSKeys.EPILOGUE, {})[prompt_key] = epilogue
        return answer
    # TODO: Catch and handle specific exception here
    except SdkRateLimitError as e:
        raise RateLimitError(f"Rate limit error. {str(e)}") from e
    except SdkError as e:
        logger.error(f"Error fetching response for prompt: {e}.")
        # TODO: Publish this error as a FE update
        raise APIError(str(e)) from e


def extract_table(
    output: dict[str, Any],
    plugins: dict[str, dict[str, Any]],
    structured_output: dict[str, Any],
    llm: LLM,
    enforce_type: str,
) -> dict[str, Any]:
    table_settings = output[PSKeys.TABLE_SETTINGS]
    table_extractor: dict[str, Any] = plugins.get("table-extractor", {})
    if not table_extractor:
        raise APIError(
            "Unable to extract table details. "
            "Please contact admin to resolve this issue."
        )
    try:
        answer = table_extractor["entrypoint_cls"].extract_large_table(
            llm=llm, table_settings=table_settings, enforce_type=enforce_type
        )
        structured_output[output[PSKeys.NAME]] = answer
        # We do not support summary and eval for table.
        # Hence returning the result
        return structured_output
    except table_extractor["exception_cls"] as e:
        msg = f"Couldn't extract table. {e}"
        raise APIError(message=msg)
