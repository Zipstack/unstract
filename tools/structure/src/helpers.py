import datetime
import logging
from collections.abc import Callable
from typing import Any

from constants import IndexingConstants as IKeys
from constants import SettingsKeys  # type: ignore [attr-defined]

from unstract.sdk.prompt import PromptTool
from unstract.sdk.tool.base import BaseTool

logger = logging.getLogger(__name__)


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

        logger.info(f"Prompt service payload for text extraction:\n{payload}")

        prompt_tool = PromptTool(
            tool=tool,
            prompt_host=tool.get_env_or_die(SettingsKeys.PROMPT_HOST),
            prompt_port=tool.get_env_or_die(SettingsKeys.PROMPT_PORT),
            request_id=run_id,
        )
        return prompt_tool.extract(payload=payload)

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

        sensitive_keys = [IKeys.EXTRACTED_TEXT]
        payload_to_log = {k: v for k, v in payload.items() if k not in sensitive_keys}
        logger.info(f"Prompt service payload for indexing:\n{payload_to_log}")
        responder = PromptTool(
            tool=tool,
            prompt_host=tool.get_env_or_die(SettingsKeys.PROMPT_HOST),
            prompt_port=tool.get_env_or_die(SettingsKeys.PROMPT_PORT),
            request_id=run_id,
        )
        return responder.index(payload=payload)

    @staticmethod
    def handle_profile_overrides(
        tool: BaseTool,
        llm_profile_to_override: dict,
        llm_profile_id: str,
        tool_metadata: dict,
        apply_profile_overrides_func: Callable[[dict, dict], list[str]],
    ) -> None:
        """Handle profile overrides and logging.

        Args:
            tool: The tool instance for logging
            llm_profile_to_override: The profile data to apply, or None if no profile
            llm_profile_id: The profile ID for logging purposes
            tool_metadata: The tool metadata dictionary to modify
            apply_profile_overrides_func: Function to apply profile overrides
        """
        if llm_profile_to_override:
            tool.stream_log(
                f"Applying profile overrides from profile: {llm_profile_to_override.get('profile_name', llm_profile_id)}"
            )
            changes = apply_profile_overrides_func(tool_metadata, llm_profile_to_override)
            if changes:
                tool.stream_log("Profile overrides applied successfully. Changes made:")
                for change in changes:
                    tool.stream_log(f"  - {change}")
            else:
                tool.stream_log(
                    "Profile overrides applied - no changes needed (values already matched)"
                )

    @staticmethod
    def elapsed_time(start_time) -> float:
        """Returns the elapsed time since the process was started."""
        return (datetime.datetime.now() - start_time).total_seconds()
