from typing import Any

from unstract.prompt_service.constants import ExecutionSource
from unstract.prompt_service.constants import IndexingConstants as IKeys
from unstract.prompt_service.exceptions import ExtractionError
from unstract.prompt_service.helpers.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.prompt_service.utils.file_utils import FileUtils
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.x2text.constants import X2TextConstants
from unstract.sdk.adapters.x2text.llm_whisperer.src import LLMWhisperer
from unstract.sdk.adapters.x2text.llm_whisperer_v2.src import LLMWhispererV2
from unstract.sdk.utils import ToolUtils
from unstract.sdk.utils.common_utils import log_elapsed
from unstract.sdk.x2txt import TextExtractionResult, X2Text


class ExtractionService:
    @staticmethod
    @log_elapsed(operation="EXTRACTION")
    def perform_extraction(
        x2text_instance_id: str,
        file_path: str,
        run_id: str,
        platform_key: str,
        output_file_path: str | None = None,
        enable_highlight: bool = False,
        usage_kwargs: dict[Any, Any] = {},
        tags: list[str] | None = None,
        execution_source: str | None = None,
        tool_exec_metadata: dict[str, Any] | None = None,
        execution_run_data_folder: str | None = None,
    ) -> str:
        extracted_text = ""
        util = PromptServiceBaseTool(platform_key=platform_key)
        x2text = X2Text(
            tool=util, adapter_instance_id=x2text_instance_id, usage_kwargs=usage_kwargs
        )
        fs = FileUtils.get_fs_instance(execution_source=execution_source)
        try:
            if enable_highlight and (
                isinstance(x2text.x2text_instance, LLMWhisperer)
                or isinstance(x2text.x2text_instance, LLMWhispererV2)
            ):
                process_response: TextExtractionResult = x2text.process(
                    input_file_path=file_path,
                    output_file_path=output_file_path,
                    enable_highlight=enable_highlight,
                    tags=tags,
                    fs=fs,
                )
                ExtractionService.update_exec_metadata(
                    fs,
                    execution_source,
                    tool_exec_metadata,
                    execution_run_data_folder,
                    process_response,
                )
            else:
                process_response: TextExtractionResult = x2text.process(
                    input_file_path=file_path,
                    output_file_path=output_file_path,
                    tags=tags,
                    fs=fs,
                )
            extracted_text = process_response.extracted_text
            return extracted_text
        except AdapterError as e:
            msg = f"Error from text extractor '{x2text.x2text_instance.get_name()}'. "
            msg += str(e)
            code = e.status_code if e.status_code != -1 else 500
            raise ExtractionError(msg, code=code) from e

    @staticmethod
    def update_exec_metadata(
        fs,
        execution_source,
        tool_exec_metadata,
        execution_run_data_folder,
        process_response,
    ):
        if execution_source == ExecutionSource.TOOL.value:
            whisper_hash_value = process_response.extraction_metadata.whisper_hash
            metadata = {X2TextConstants.WHISPER_HASH: whisper_hash_value}
            for key, value in metadata.items():
                tool_exec_metadata[key] = value
            metadata_path = execution_run_data_folder / IKeys.METADATA_FILE
            ToolUtils.dump_json(
                file_to_dump=metadata_path,
                json_to_dump=metadata,
                fs=fs,
            )
