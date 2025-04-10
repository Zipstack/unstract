from typing import Any

from constants import IndexingConstants as IKeys
from constants import SettingsKeys  # type: ignore [attr-defined]

from unstract.sdk.prompt import PromptTool
from unstract.sdk.tool.base import BaseTool


class StructureToolHelper:
    @staticmethod
    def dynamic_extraction(
        file_path: str,
        enable_highlight: bool,
        usage_kwargs: dict[str, Any],
        run_id: str,
        tool_settings: dict[str, Any],
        extract_file_path: str,
        tool: BaseTool,
        execution_run_data_folder: str,
    ) -> str:
        x2text = tool_settings[SettingsKeys.X2TEXT_ADAPTER]
        tool.stream_log(f"Extracting text from {file_path} into {extract_file_path}")
        payload = {
            IKeys.X2TEXT_INSTANCE_ID: x2text,
            IKeys.FILE_PATH: file_path,
            IKeys.ENABLE_HIGHLIGHT: enable_highlight,
            IKeys.USAGE_KWARGS: usage_kwargs.copy(),
            IKeys.RUN_ID: run_id,
            IKeys.EXECUTION_SOURCE: SettingsKeys.TOOL,
            IKeys.OUTPUT_FILE_PATH: str(extract_file_path),
            IKeys.TAGS: tool.tags,
            IKeys.TOOL_EXECUTION_METATADA: tool.get_exec_metadata,
            IKeys.EXECUTION_DATA_DIR: str(execution_run_data_folder),
        }

        tool.stream_log(f"Payload constructed : {payload}")
        responder = PromptTool(
            tool=tool,
            prompt_host=tool.get_env_or_die(SettingsKeys.PROMPT_HOST),
            prompt_port=tool.get_env_or_die(SettingsKeys.PROMPT_PORT),
        )
        tool.stream_log(f"responder : {responder}")
        extracted_text = responder.extract(payload=payload)

        return extracted_text

    @staticmethod
    def dynamic_indexing(
        file_path: str,
        tool_settings: dict[str, Any],
        run_id: str,
        tool: BaseTool,
        execution_run_data_folder: str,
        reindex: bool,
        usage_kwargs: dict[str, Any],
        enable_highlight: bool,
        chunk_size: int,
        chunk_overlap: int,
        file_hash: str | None = None,
        tool_id: str = None,
        extracted_text: str = None,
    ) -> str:
        x2text = tool_settings[SettingsKeys.X2TEXT_ADAPTER]

        payload = {
            IKeys.TOOL_ID: tool_id,
            IKeys.EMBEDDING_INSTANCE_ID: tool_settings[SettingsKeys.EMBEDDING],
            IKeys.VECTOR_DB_INSTANCE_ID: tool_settings[SettingsKeys.VECTOR_DB],
            IKeys.X2TEXT_INSTANCE_ID: x2text,
            IKeys.FILE_HASH: file_hash,
            IKeys.CHUNK_SIZE: chunk_size,
            IKeys.CHUNK_OVERLAP: chunk_overlap,
            IKeys.REINDEX: reindex,
            IKeys.FILE_PATH: str(file_path),
            IKeys.ENABLE_HIGHLIGHT: enable_highlight,
            IKeys.USAGE_KWARGS: usage_kwargs.copy(),
            IKeys.RUN_ID: run_id,
            IKeys.EXECUTION_SOURCE: SettingsKeys.TOOL,
            IKeys.TAGS: tool.tags,
            IKeys.TOOL_EXECUTION_METATADA: tool.get_exec_metadata,
            IKeys.EXECUTION_DATA_DIR: str(execution_run_data_folder),
            IKeys.EXTRACTED_TEXT: extracted_text,
        }

        responder = PromptTool(
            tool=tool,
            prompt_host=tool.get_env_or_die(SettingsKeys.PROMPT_HOST),
            prompt_port=tool.get_env_or_die(SettingsKeys.PROMPT_PORT),
        )
        doc_id = responder.index(payload=payload)
        return doc_id
