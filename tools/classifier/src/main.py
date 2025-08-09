import sys
from typing import Any

from helper import ClassifierHelper  # type: ignore
from helper import ReservedBins

from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.constants import (
        Common,
        LogLevel,
        LogState,
        MetadataKey,
        ToolSettingsKey,
        UsageKwargs,
    )
    from unstract.sdk1.exceptions import SdkError
    from unstract.sdk1.llm import LLM
    from unstract.sdk1.tool.base import BaseTool
    from unstract.sdk1.tool.entrypoint import ToolEntrypoint
else:
    from unstract.sdk.constants import (
        LogLevel,
        LogState,
        MetadataKey,
        ToolSettingsKey,
        UsageKwargs,
    )
    from unstract.sdk.exceptions import SdkError
    from unstract.sdk.llm import LLM
    from unstract.sdk.tool.base import BaseTool
    from unstract.sdk.tool.entrypoint import ToolEntrypoint


class UnstractClassifier(BaseTool):
    def __init__(self, log_level: str = LogLevel.INFO) -> None:
        super().__init__(log_level)

    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        bins: list[str] | None = settings.get("classificationBins")
        llm_adapter_instance_id = settings.get(ToolSettingsKey.LLM_ADAPTER_ID)
        text_extraction_adapter_id = settings.get("textExtractorId")
        if not bins:
            self.stream_error_and_exit("Classification bins are required.")
        elif len(bins) < 2:
            self.stream_error_and_exit("At least two classification bins are required.")
        elif ReservedBins.UNKNOWN in bins:
            self.stream_error_and_exit(
                f"Classification bin '{ReservedBins.UNKNOWN}' is reserved to mark "
                "files which cannot be classified."
            )

        if not llm_adapter_instance_id:
            self.stream_error_and_exit("Choose an LLM to perform the classification.")
        if not text_extraction_adapter_id:
            self.stream_error_and_exit(
                "Choose a text extractor to extract the documents."
            )

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
        self.helper = ClassifierHelper(tool=self, output_dir=output_dir)

        # Update GUI
        input_log = f"### Classification bins:\n```text\n{bins}\n```\n\n"
        output_log = ""
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        self.stream_log(f"Reading file... {input_file}")
        text: str | None = self.helper.extract_text(
            file=input_file,
            text_extraction_adapter_id=text_extraction_adapter_id,
        )
        if not text:
            self.helper.stream_error_and_exit("Unable to extract text")
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

        if ReservedBins.UNKNOWN not in bins:
            bins.append(ReservedBins.UNKNOWN)
        bins_with_quotes = [f"'{b}'" for b in bins]

        usage_kwargs: dict[Any, Any] = dict()
        usage_kwargs[UsageKwargs.WORKFLOW_ID] = self.workflow_id
        usage_kwargs[UsageKwargs.EXECUTION_ID] = self.execution_id
        usage_kwargs[UsageKwargs.FILE_NAME] = self.source_file_name
        usage_kwargs[UsageKwargs.RUN_ID] = self.file_execution_id

        try:
            if check_feature_flag_status("sdk1"):
                llm = LLM(
                    adapter_instance_id=llm_adapter_instance_id,
                    tool=self,
                    kwargs=usage_kwargs,
                )
            else:
                llm = LLM(
                    tool=self,
                    adapter_instance_id=llm_adapter_instance_id,
                    usage_kwargs=usage_kwargs,
                )
        except SdkError:
            self.helper.stream_error_and_exit("Unable to get llm instance")
            return

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
            "Your categorization should be strictly exactly one of the items in the "  # noqa: E501
            "categories given, do not provide any explanation. Find a semantic match of category if possible. "  # noqa: E501
            "If it does not categorize well into any of the listed categories, categorize it as 'unknown'."  # noqa: E501
            f"Do not enclose the result within single quotes.\n\nText:\n\n{text}\n\n\nCategory:"  # noqa: E501
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
        self.helper.copy_source_to_output_bin(
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


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = UnstractClassifier.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
