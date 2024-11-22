import ast
import sys
from pathlib import Path
from typing import Any

from unstract.sdk.constants import LogState, MetadataKey
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint
from unstract.sdk.x2txt import TextExtractionResult, X2Text


class TextExtractor(BaseTool):

    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        """Validate the input file and settings.

        Args:
            input_file (str): The path to the input file.
            settings (dict[str, Any]): The settings for the tool.
        """
        text_extraction_adapter_id = settings["extractorId"]
        if not text_extraction_adapter_id:
            self.stream_error_and_exit(
                "Adaptor id not found, please select adaptor for extractor tool"
            )

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        """Run the text extraction process.

        Args:
            settings (dict[str, Any]): The settings for the tool.
            input_file (str): The path to the input file.
            output_dir (str): The path to the output directory.

        Raises:
            Exception: If there is an error creating/writing the output file.

        Returns:
            None
        """
        text_extraction_adapter_id = settings["extractorId"]
        source_name = self.get_exec_metadata.get(MetadataKey.SOURCE_NAME)

        self.stream_log(
            f"Extractor ID: {text_extraction_adapter_id} "
            "has been retrieved from settings."
        )

        input_log = f"Processing file: \n\n`{source_name}`"
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)

        text_extraction_adapter = X2Text(
            tool=self, adapter_instance_id=text_extraction_adapter_id
        )
        self.stream_log("Text extraction adapter has been created successfully.")
        extraction_result: TextExtractionResult = text_extraction_adapter.process(
            input_file_path=input_file
        )
        extracted_text = self.convert_to_actual_string(extraction_result.extracted_text)

        self.stream_log("Text has been extracted successfully.")

        first_5_lines = "\n\n".join(extracted_text.split("\n")[:5])
        output_log = f"### Text\n\n```text\n{first_5_lines}\n```\n\n...(truncated)"
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        try:
            self.stream_log("Preparing to write the extracted text.")
            if source_name:
                output_path = Path(output_dir) / f"{Path(source_name).stem}.txt"
                if hasattr(self, "workflow_filestorage"):
                    self.workflow_filestorage.write(
                        path=output_path, mode="w", data=extracted_text
                    )
                else:
                    with open(output_path, "w", encoding="utf-8") as file:
                        file.write(extracted_text)

                self.stream_log("Tool output written successfully.")
            else:
                self.stream_error_and_exit(
                    "Error creating/writing output file: source_name not found"
                )
        except Exception as e:
            self.stream_error_and_exit(f"Error creating/writing output file: {e}")
        self.write_tool_result(data=extracted_text)

    def convert_to_actual_string(self, text: Any) -> str:
        if isinstance(text, bytes):
            return text.decode("utf-8")
        elif isinstance(text, str):
            if text.startswith("b'") and text.endswith("'"):
                bytes_text: bytes = ast.literal_eval(text)
                return bytes_text.decode("utf-8")
            else:
                return text
        else:
            return str(text)


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = TextExtractor.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
