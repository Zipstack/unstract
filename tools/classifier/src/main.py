import shutil
import sys
from pathlib import Path
from typing import Any

from helper import ClassifierHelper
from llama_index import set_global_service_context
from unstract.sdk.cache import ToolCache
from unstract.sdk.constants import LogLevel, LogState, MetadataKey, ToolEnv
from unstract.sdk.llm import ToolLLM
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint
from unstract.sdk.utils import ToolUtils
from unstract.sdk.utils.service_context import ServiceContext


class UnstractClassifier(BaseTool):
    def __init__(self, log_level: str = LogLevel.INFO) -> None:
        super().__init__(log_level)
        self.helper = ClassifierHelper(tool=self)

    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        bins = settings["classificationBins"]

        if len(bins) < 2:
            self.stream_error_and_exit("At least two bins are required")

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        bins = settings["classificationBins"]
        use_cache = settings["useCache"]

        # Update GUI
        input_log = f"### Classification bins:\n```text\n{bins}\n```\n\n"
        output_log = ""
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        self.stream_log("Reading file...")
        text = self.helper.extract_text(input_file)
        self.stream_log(f"Text length: {len(text)}")

        # Update GUI
        input_text_for_log = text
        if len(input_text_for_log) > 500:
            input_text_for_log = input_text_for_log[:500] + "...(truncated)"
        input_log = (
            f"### Classification bins:\n```text\n{bins}\n```\n\n"
            f"### Input text:\n\n```text\n{input_text_for_log}\n```\n\n"
        )
        output_log = ""
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        if "unknown" not in bins:
            bins.append("unknown")
        bins_with_quotes = [f"'{b}'" for b in bins]

        tool_llm = ToolLLM(tool=self, tool_settings=settings)
        llm = tool_llm.get_llm()
        if not llm:
            self.stream_error_and_exit("Unable to get llm instance")
        service_context = ServiceContext.get_service_context(
            platform_api_key=self.get_env_or_die(ToolEnv.PLATFORM_API_KEY),
            llm=llm,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
        )
        set_global_service_context(service_context)

        max_tokens = tool_llm.get_max_tokens(reserved_for_output=50 + 1000)
        max_bytes = int(max_tokens * 1.3)
        self.stream_log(
            f"LLM Max tokens: {max_tokens} ==> Max bytes: {max_bytes}"
        )
        self.stream_log(
            f"LLM Max tokens: {max_tokens} ==> Max bytes: {max_bytes}"
        )
        limited_text = ""
        for byte in text.encode():
            if len(limited_text.encode()) < max_bytes:
                limited_text += chr(byte)
            else:
                break
        text = limited_text
        self.stream_log(f"Length of text: {len(text.encode())} {len(text)}")

        prompt = (
            f"Classify the following text into one of the following categories: {' '.join(bins_with_quotes)}.\n\n"  # noqa: E501
            f"Your categorization should be strictly exactly one of the items in the "  # noqa: E501
            f"Your categorization should be strictly exactly one of the items in the "  # noqa: E501
            f"categories given. Find a semantic match of category if possible. If it does not categorize well "  # noqa: E501
            f"into any of the listed categories, categorize it as 'unknown'.\n\nText:\n\n{text}\n\n\nCategory:"  # noqa: E501
        )

        settings_string = "".join(str(value) for value in settings.values())
        cache_key = (
            f"cache:{self.workflow_id}:{ToolUtils.hash_str(settings_string)}:"
            f"{ToolUtils.hash_str(prompt)}"
        )

        classification = None
        if use_cache:
            cache = ToolCache(
                tool=self,
                platform_host=self.get_env_or_die(ToolEnv.PLATFORM_HOST),
                platform_port=int(self.get_env_or_die(ToolEnv.PLATFORM_PORT)),
            )
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                classification = cached_response
                self.stream_cost(cost=0.0, cost_units="cache")

        if classification is None:
            self.stream_log("Calling LLM")
            try:
                response = llm.complete(prompt, max_tokens=50, stop=["\n"])
                if response is None:
                    self.stream_error_and_exit("Error calling LLM")
                classification = response.text.strip()
                self.stream_log(f"LLM response: {response}")
            except Exception as e:
                self.stream_error_and_exit(f"Error calling LLM: {e}")

            if use_cache:
                cache = ToolCache(
                    tool=self,
                    platform_host=self.get_env_or_die(ToolEnv.PLATFORM_HOST),
                    platform_port=int(
                        self.get_env_or_die(ToolEnv.PLATFORM_PORT)
                    ),
                )
                cache.set(cache_key, classification)

        classification = classification.lower()  # type: ignore
        bins = [bin.lower() for bin in bins]

        if classification not in bins:
            self.stream_error_and_exit(
                f"Invalid classification done: {classification}"
            )
        if not classification:
            classification = "unknown"

        source_name = self.get_exec_metadata.get(MetadataKey.SOURCE_NAME)
        self._copy_input_to_output_bin(
            output_dir=output_dir,
            classification=classification,
            source_file=self.get_source_file(),
            source_name=source_name,
        )
        output_log = "### Classifier output\n\n"
        output_log += f"```bash\nCLASSIFICATION={classification}\n```\n\n"
        self.stream_single_step_message(output_log)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        classification_dict = {
            "input_file": source_name,
            "result": classification,
        }
        self.write_tool_result(data=classification_dict)

    def _copy_input_to_output_bin(
        self,
        output_dir: str,
        classification: str,
        source_file: str,
        source_name: str,
    ) -> None:
        """Method to save result in output folder and the data directory.

        Args:
            output_dir (str): Output directory in TOOL_DATA_DIR
            classification (str): classification result
            source_file (str): Path to source file used in the workflow
            source_name (str): Name of the actual input from the source
        """
        try:
            output_folder_bin = Path(output_dir) / classification
            if not output_folder_bin.is_dir():
                output_folder_bin.mkdir(parents=True, exist_ok=True)

            output_file = output_folder_bin / source_name
            shutil.copyfile(source_file, output_file)
        except Exception as e:
            self.stream_error_and_exit(f"Error creating output file: {e}")


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = UnstractClassifier.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
