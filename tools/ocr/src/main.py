import sys
import time
from pathlib import Path
from typing import Any

from helper import OcrHelper
from unstract.sdk.cache import ToolCache
from unstract.sdk.constants import LogLevel, LogState, MetadataKey, ToolEnv
from unstract.sdk.ocr import OCR
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint
from unstract.sdk.tool.validator import ToolValidator
from unstract.sdk.utils.tool_utils import ToolUtils


class UnstractOCR(BaseTool):
    def __init__(self, log_level: str = LogLevel.INFO) -> None:
        super().__init__(log_level)
        self.helper = OcrHelper(tool=self)
        self.validator = ToolValidator(tool=self)

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        # Initializing Function Arguments
        use_cache = settings["useCache"]
        ocr_adapter_id = settings["ocrAdapterId"]

        # Set adapter
        tool_ocr = OCR(tool=self)
        ocr_adapter = tool_ocr.get_ocr(adapter_instance_id=ocr_adapter_id)

        # Read image file into memory
        with open(input_file, "rb") as image_file:
            image_content = image_file.read()

        input_file_type_mime = ToolUtils.get_file_mime_type(Path(input_file))

        # Construct an image object
        output_log = ""
        input_log = f"Input file: `{input_file}`\n\n"
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)

        # Check cache
        content_hash = ToolUtils.get_hash_from_file(file_path=input_file)
        cache_key = (
            f"cache:{self.workflow_id}:{ocr_adapter.get_name()}:{content_hash}"
        )

        result_text = None
        if use_cache:
            cache = ToolCache(
                tool=self,
                platform_host=self.get_env_or_die(ToolEnv.PLATFORM_HOST),
                platform_port=int(self.get_env_or_die(ToolEnv.PLATFORM_PORT)),
            )
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                result_text = cached_response
                self.stream_cost(cost=0.0, cost_units="cache")
        cached_result = True if result_text else False
        # Process if not cached
        if not result_text:
            result_text = ""
            t1 = time.time()
            result_text = ocr_adapter.process(input_file_path=input_file)
            t2 = time.time()
            self.helper.time_taken(start_time=t1, end_time=t2)

        # Pre-process and cache result
        self.helper.set_result_in_cache(
            key=cache_key, result=result_text, cached_result=cached_result
        )
        self.helper.calculate_cost(
            file=image_content,
            file_type_mime=input_file_type_mime,
            cached_result=cached_result,
        )
        self.helper.stream_output_text_log(result_text)

        # Write result to file
        self.stream_log("Writing tool output")
        source_name = self.get_exec_metadata.get(MetadataKey.SOURCE_NAME)
        output_path = Path(output_dir) / f"{Path(source_name).stem}.txt"
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result_text)
        except Exception as e:
            self.stream_error_and_exit(f"Error creating output file: {e}")

        # Log output
        if len(result_text) > 1000:
            output_log = (
                f"```text\n{result_text[:1000]}... (truncated)\n```\n\n"
            )
        else:
            output_log = f"```text\n{result_text}\n```\n\n"
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)
        self.stream_single_step_message(output_log)
        self.write_tool_result(data=result_text)


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = UnstractOCR.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
