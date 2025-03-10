from typing import Any, Optional

from unstract.prompt_service_v2.helper.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.x2text.constants import X2TextConstants
from unstract.sdk.adapters.x2text.llm_whisperer.src import LLMWhisperer
from unstract.sdk.adapters.x2text.llm_whisperer_v2.src import LLMWhispererV2
from unstract.sdk.exceptions import X2TextError
from unstract.sdk.file_storage import FileStorage, FileStorageProvider
from unstract.sdk.utils.common_utils import capture_metrics, log_elapsed
from unstract.sdk.x2txt import TextExtractionResult, X2Text


class ExtractionService:

    @staticmethod
    @capture_metrics
    @log_elapsed(operation="EXTRACTION")
    def perform_extraction(
        x2text_instance_id: str,
        file_path: str,
        run_id: str,
        platform_key: str,
        output_file_path: Optional[str] = None,
        enable_highlight: bool = False,
        usage_kwargs: dict[Any, Any] = {},
        fs: FileStorage = FileStorage(FileStorageProvider.LOCAL),
        tags: Optional[list[str]] = None,
    ) -> str:

        extracted_text = ""
        util = PromptServiceBaseTool(platform_key=platform_key)
        x2text = X2Text(
            tool=util, adapter_instance_id=x2text_instance_id, usage_kwargs=usage_kwargs
        )
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
                whisper_hash_value = process_response.extraction_metadata.whisper_hash
                metadata = {X2TextConstants.WHISPER_HASH: whisper_hash_value}
                if hasattr(self.tool, "update_exec_metadata"):
                    self.tool.update_exec_metadata(metadata)
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
            raise X2TextError(msg) from e

        # TODO : Handle runId
        # TODO: Revisit passage of tool through SDK
        # TODO : Revisit usgae of update_exec_metadata
        # TODO : Process Text callable
