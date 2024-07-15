import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from helper import ClassifierHelper  # type: ignore
from unstract.sdk.core.constants import LogLevel, LogState, MetadataKey, ToolSettingsKey
from unstract.sdk.core.exceptions import SdkError
from unstract.sdk.core.llm import LLM
from unstract.sdk.core.tool.base import BaseTool
from unstract.sdk.core.tool.entrypoint import ToolEntrypoint


class UnstractClassifier(BaseTool):
    def __init__(self, log_level: str = LogLevel.INFO) -> None:
        super().__init__(log_level)
        self.helper = ClassifierHelper(tool=self)

    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        bins: Optional[list[str]] = settings.get("classificationBins")
        llm_adapter_instance_id = settings.get(ToolSettingsKey.LLM_ADAPTER_ID)
        text_extraction_adapter_id = settings.get("textExtractorId")
        if not bins:
            self.stream_error_and_exit("Classification bins are required")
        elif len(bins) < 2:
            self.stream_error_and_exit("At least two bins are required")
        if not llm_adapter_instance_id:
            self.stream_error_and_exit("Choose an LLM to process the classifier")
        if not text_extraction_adapter_id:
            self.stream_error_and_exit("Choose an LLM to extract the documents")

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        bins = settings["classificationBins"]
        use_cache = settings["useCache"]
        text_extraction_adapter_id = settings["textExtractorId"]
        llm_adapter_instance_id = settings[ToolSettingsKey.LLM_ADAPTER_ID]

        # Update GUI
        input_log = f"### Classification bins:\n```text\n{bins}\n```\n\n"
        output_log = ""
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        self.stream_log(f"Reading file... {input_file}")
        text: Optional[str] = self.helper.extract_text(
            file=input_file,
            text_extraction_adapter_id=text_extraction_adapter_id,
        )
        if not text:
            self.stream_error_and_exit("Unable to extract text")
            return
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

        usage_kwargs: dict[Any, Any] = dict()
        usage_kwargs["workflow_id"] = self.workflow_id
        usage_kwargs["execution_id"] = self.execution_id

        try:
            llm = LLM(
                tool=self,
                adapter_instance_id=llm_adapter_instance_id,
                usage_kwargs=usage_kwargs,
            )
        except SdkError:
            self.stream_error_and_exit("Unable to get llm instance")

        max_tokens = llm.get_max_tokens(reserved_for_output=50 + 1000)
        max_bytes = int(max_tokens * 1.3)
        self.stream_log(f"LLM Max tokens: {max_tokens} ==> Max bytes: {max_bytes}")
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
            f"categories given. Find a semantic match of category if possible. If it does not categorize well "  # noqa: E501
            f"into any of the listed categories, categorize it as 'unknown'.\n\nText:\n\n{text}\n\n\nCategory:"  # noqa: E501
        )

        settings_string = "".join(str(value) for value in settings.values())
        classification = self.helper.find_classification(
            use_cache=use_cache,
            settings_string=settings_string,
            prompt=prompt,
            bins=bins,
            llm=llm,
        )

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
