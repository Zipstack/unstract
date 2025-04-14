from logging import Logger
from typing import Any

from flask import current_app as app

from unstract.core.flask.exceptions import APIError
from unstract.prompt_service.constants import ExecutionSource, FileStorageKeys
from unstract.prompt_service.constants import PromptServiceConstants as PSKeys
from unstract.prompt_service.exceptions import RateLimitError
from unstract.prompt_service.helpers.plugin import PluginManager
from unstract.sdk.exceptions import RateLimitError as SdkRateLimitError
from unstract.sdk.exceptions import SdkError
from unstract.sdk.file_storage import FileStorage, FileStorageProvider
from unstract.sdk.file_storage.constants import StorageType
from unstract.sdk.file_storage.env_helper import EnvHelper
from unstract.sdk.llm import LLM


class AnswerPromptService:
    @staticmethod
    def extract_variable(
        structured_output: dict[str, Any],
        variable_names: list[Any],
        output: dict[str, Any],
        promptx: str,
    ) -> str:
        logger: Logger = app.logger
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

    @staticmethod
    def construct_and_run_prompt(
        tool_settings: dict[str, Any],
        output: dict[str, Any],
        llm: LLM,
        context: str,
        prompt: str,
        metadata: dict[str, Any],
        file_path: str = "",
        execution_source: str | None = ExecutionSource.IDE.value,
    ) -> str:
        platform_postamble = tool_settings.get(PSKeys.PLATFORM_POSTAMBLE, "")
        summarize_as_source = tool_settings.get(PSKeys.SUMMARIZE_AS_SOURCE)
        enable_highlight = tool_settings.get(PSKeys.ENABLE_HIGHLIGHT, False)
        if not enable_highlight or summarize_as_source:
            platform_postamble = ""
        prompt = AnswerPromptService.construct_prompt(
            preamble=tool_settings.get(PSKeys.PREAMBLE, ""),
            prompt=output[prompt],
            postamble=tool_settings.get(PSKeys.POSTAMBLE, ""),
            grammar_list=tool_settings.get(PSKeys.GRAMMAR, []),
            context=context,
            platform_postamble=platform_postamble,
        )
        return AnswerPromptService.run_completion(
            llm=llm,
            prompt=prompt,
            metadata=metadata,
            prompt_key=output[PSKeys.NAME],
            prompt_type=output.get(PSKeys.TYPE, PSKeys.TEXT),
            enable_highlight=enable_highlight,
            file_path=file_path,
            execution_source=execution_source,
        )

    @staticmethod
    def construct_prompt(
        preamble: str,
        prompt: str,
        postamble: str,
        grammar_list: list[dict[str, Any]],
        context: str,
        platform_postamble: str,
    ) -> str:
        prompt = f"{preamble}\n\nQuestion or Instruction: {prompt}"
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
        prompt += (
            f"\n\n{postamble}\n\nContext:\n---------------\n{context}\n"
            f"-----------------\n\n{platform_postamble}Answer:"
        )
        return prompt

    @staticmethod
    def run_completion(
        llm: LLM,
        prompt: str,
        metadata: dict[str, str] | None = None,
        prompt_key: str | None = None,
        prompt_type: str | None = PSKeys.TEXT,
        enable_highlight: bool = False,
        file_path: str = "",
        execution_source: str | None = None,
    ) -> str:
        logger: Logger = app.logger
        try:
            highlight_data_plugin: dict[str, Any] = PluginManager().get_plugin(
                PSKeys.HIGHLIGHT_DATA_PLUGIN
            )
            highlight_data = None
            if highlight_data_plugin and enable_highlight:
                fs_instance: FileStorage = FileStorage(FileStorageProvider.LOCAL)
                if execution_source == ExecutionSource.IDE.value:
                    fs_instance = EnvHelper.get_storage(
                        storage_type=StorageType.PERMANENT,
                        env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
                    )
                if execution_source == ExecutionSource.TOOL.value:
                    fs_instance = EnvHelper.get_storage(
                        storage_type=StorageType.SHARED_TEMPORARY,
                        env_name=FileStorageKeys.TEMPORARY_REMOTE_STORAGE,
                    )
                highlight_data = highlight_data_plugin["entrypoint_cls"](
                    file_path=file_path,
                    fs_instance=fs_instance,
                ).run
            completion = llm.complete(
                prompt=prompt,
                process_text=highlight_data,
                extract_json=prompt_type.lower() != PSKeys.TEXT,
            )
            answer: str = completion[PSKeys.RESPONSE].text
            highlight_data = completion.get(PSKeys.HIGHLIGHT_DATA, [])
            confidence_data = completion.get(PSKeys.CONFIDENCE_DATA)
            line_numbers = completion.get(PSKeys.LINE_NUMBERS, [])
            whisper_hash = completion.get(PSKeys.WHISPER_HASH, "")
            if metadata is not None and prompt_key:
                metadata.setdefault(PSKeys.HIGHLIGHT_DATA, {})[prompt_key] = (
                    highlight_data
                )
                metadata.setdefault(PSKeys.LINE_NUMBERS, {})[prompt_key] = line_numbers
                metadata[PSKeys.WHISPER_HASH] = whisper_hash
                if confidence_data:
                    metadata.setdefault(PSKeys.CONFIDENCE_DATA, {})[prompt_key] = (
                        confidence_data
                    )
            return answer
        # TODO: Catch and handle specific exception here
        except SdkRateLimitError as e:
            raise RateLimitError(f"Rate limit error. {str(e)}") from e
        except SdkError as e:
            logger.error(f"Error fetching response for prompt: {e}.")
            # TODO: Publish this error as a FE update
            raise APIError(str(e)) from e

    @staticmethod
    def extract_table(
        output: dict[str, Any],
        structured_output: dict[str, Any],
        llm: LLM,
        enforce_type: str,
        execution_source: str,
    ) -> dict[str, Any]:
        table_settings = output[PSKeys.TABLE_SETTINGS]
        table_extractor: dict[str, Any] = PluginManager().get_plugin("table-extractor")
        if not table_extractor:
            raise APIError(
                "Unable to extract table details. "
                "Please contact admin to resolve this issue."
            )
        fs_instance: FileStorage = FileStorage(FileStorageProvider.LOCAL)
        if execution_source == ExecutionSource.IDE.value:
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )
        if execution_source == ExecutionSource.TOOL.value:
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.SHARED_TEMPORARY,
                env_name=FileStorageKeys.TEMPORARY_REMOTE_STORAGE,
            )
        try:
            answer = table_extractor["entrypoint_cls"].extract_large_table(
                llm=llm,
                table_settings=table_settings,
                enforce_type=enforce_type,
                fs_instance=fs_instance,
            )
            structured_output[output[PSKeys.NAME]] = answer
            # We do not support summary and eval for table.
            # Hence returning the result
            return structured_output
        except table_extractor["exception_cls"] as e:
            msg = f"Couldn't extract table. {e}"
            raise APIError(message=msg)

    @staticmethod
    def extract_line_item(
        tool_settings: dict[str, Any],
        output: dict[str, Any],
        structured_output: dict[str, Any],
        llm: LLM,
        file_path: str,
        metadata: dict[str, str] | None,
        execution_source: str,
    ) -> dict[str, Any]:
        line_item_extraction_plugin: dict[str, Any] = PluginManager().get_plugin(
            "line-item-extraction"
        )
        if not line_item_extraction_plugin:
            raise APIError(PSKeys.PAID_FEATURE_MSG)

        extract_file_path = file_path

        # Read file content into context
        fs_instance: FileStorage = FileStorage(FileStorageProvider.LOCAL)
        if execution_source == ExecutionSource.IDE.value:
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )
        if execution_source == ExecutionSource.TOOL.value:
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.SHARED_TEMPORARY,
                env_name=FileStorageKeys.TEMPORARY_REMOTE_STORAGE,
            )

        if not fs_instance.exists(extract_file_path):
            raise FileNotFoundError(
                f"The file at path '{extract_file_path}' does not exist."
            )
        context = fs_instance.read(path=extract_file_path, encoding="utf-8", mode="r")

        prompt = AnswerPromptService.construct_prompt(
            preamble=tool_settings.get(PSKeys.PREAMBLE, ""),
            prompt=output["promptx"],
            postamble=tool_settings.get(PSKeys.POSTAMBLE, ""),
            grammar_list=tool_settings.get(PSKeys.GRAMMAR, []),
            context=context,
            platform_postamble="",
        )

        try:
            line_item_extraction = line_item_extraction_plugin["entrypoint_cls"](
                llm=llm,
                tool_settings=tool_settings,
                output=output,
                prompt=prompt,
                structured_output=structured_output,
            )
            answer = line_item_extraction.run()
            structured_output[output[PSKeys.NAME]] = answer
            metadata[PSKeys.CONTEXT][output[PSKeys.NAME]] = [context]
            return structured_output
        except line_item_extraction_plugin["exception_cls"] as e:
            msg = f"Couldn't extract table. {e}"
            raise APIError(message=msg)
