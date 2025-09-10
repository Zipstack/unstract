import re
from pathlib import Path
from typing import Any

from unstract.sdk.constants import LogLevel, MetadataKey, UsageKwargs
from unstract.sdk.llm import LLM
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.x2txt import TextExtractionResult, X2Text


class ReservedBins:
    UNKNOWN = "unknown"
    FAILED = "__unstract_failed"


class ClassifierHelper:
    """Helper functions for Classifier."""

    def __init__(self, tool: BaseTool, output_dir: str) -> None:
        """Creates a helper class for the Classifier tool.

        Args:
            tool (BaseTool): Base tool instance
            output_dir (str): Output directory in EXECUTION_DATA_DIR
        """
        self.tool = tool
        self.output_dir = output_dir

    def stream_error_and_exit(
        self, message: str, bin_to_copy_to: str = ReservedBins.FAILED
    ) -> None:
        """Streams error logs and performs required cleanup.

        Helper which copies files to a reserved bin in case of an error.

        Args:
            message (str): Error message to log
            bin_to_copy_to (str): The folder to copy the failed source file to.
                Defaults to `__unstract_failed`.
            input_file (Optional[str], optional): Input file to copy. Defaults to None.
            output_dir (Optional[str], optional): Output directory to copy to.
                Defaults to None.
        """
        source_name = self.tool.get_exec_metadata.get(MetadataKey.SOURCE_NAME)
        self.copy_source_to_output_bin(
            classification=bin_to_copy_to,
            source_file=self.tool.get_source_file(),
            source_name=source_name,
        )

        self.tool.stream_error_and_exit(message=message)

    def copy_source_to_output_bin(
        self,
        classification: str,
        source_file: str,
        source_name: str,
    ) -> None:
        """Method to save result in output folder and the data directory.

        Args:
            classification (str): classification result
            source_file (str): Path to source file used in the workflow
            source_name (str): Name of the actual input from the source
        """
        try:
            output_folder_bin = Path(self.output_dir) / classification
            output_file = output_folder_bin / source_name
            self._copy_file(
                source_fs=self.tool.workflow_filestorage,
                destination_fs=self.tool.workflow_filestorage,
                source_path=source_file,
                destination_path=str(output_file),
            )
        except Exception as e:
            self.tool.stream_error_and_exit(f"Error creating output file: {e}")

    def _copy_file(
        self,
        source_fs: Any,
        destination_fs: Any,
        source_path: str,
        destination_path: str,
    ) -> None:
        """Helps copy a file from source to destination.

        Args:
            src (str): Path to the source file
            dest (str): Path to the destination file
        """
        try:
            # TODO: Move it to the top once SDK released with fileStorage Feature
            # Change the source fs and destination fs type to to FileStorage
            from unstract.sdk.utils import FileStorageUtils

            FileStorageUtils.copy_file_to_destination(
                source_storage=source_fs,
                destination_storage=destination_fs,
                source_path=source_path,
                destination_paths=[destination_path],
            )
        except Exception as e:
            self.stream_error_and_exit(f"Error copying file: {e}")

    def extract_text(
        self, file: str, text_extraction_adapter_id: str | None
    ) -> str | None:
        """Extract text from file.

        Args:
            file (str): The path to the input file

        Returns:
            str: page content
        """
        if not text_extraction_adapter_id:
            return self._extract_from_file(file)

        return self._extract_from_adapter(file, text_extraction_adapter_id)

    def _extract_from_adapter(self, file: str, adapter_id: str) -> str | None:
        """Extract text from adapter.

        Args:
            file: The path to the input file
            adapter_id: The id of the adapter
        Returns:
            str: page content
        """
        self.tool.stream_log(
            f"Creating text extraction adapter using adapter_id: {adapter_id}"
        )
        usage_kwargs: dict[Any, Any] = dict()
        usage_kwargs[UsageKwargs.FILE_NAME] = self.tool.source_file_name
        usage_kwargs[UsageKwargs.RUN_ID] = self.tool.file_execution_id

        x2text = X2Text(
            tool=self.tool, adapter_instance_id=adapter_id, usage_kwargs=usage_kwargs
        )

        self.tool.stream_log("Text extraction adapter has been created successfully.")

        try:
            extraction_result: TextExtractionResult = x2text.process(
                input_file_path=file,
                fs=self.tool.workflow_filestorage,
                tags=self.tool.tags,
            )
            extracted_text: str = extraction_result.extracted_text
            return extracted_text
        except Exception as e:
            self.tool.stream_log(f"Adapter error: {e}")
            return None

    def _extract_from_file(self, file: str) -> str | None:
        """Extract text from file.

        Args:
            file: The path to the input file
        Returns:
            str: page content
        """
        self.tool.stream_log("Extracting text from file")
        try:
            text = self.tool.workflow_filestorage.read(path=file, mode="rb").decode(
                "utf-8"
            )
        except Exception as e:
            self.tool.stream_log(f"File error: {e}")
            return None

        self.tool.stream_log("Text extracted from file")
        return text

    def find_classification(
        self,
        use_cache: bool,
        settings_string: str,
        bins: list[str],
        prompt: str,
        llm: LLM,
    ) -> str | None:
        """Find classification for text.

        Args:
            use_cache (bool): Whether to use cache (deprecated, not used)
            settings_string (str): hash of settings (deprecated, not used)
            prompt (str): Prompt
            bins (list[str]): Classification Bins
            llm (LLM): LLM

        Returns:
            Optional[str]: Classification from the LLM.
        """
        self.tool.stream_log("Calling LLM for classification.")
        llm_response = self.call_llm(prompt=prompt, llm=llm)
        classification = self.clean_llm_response(llm_response=llm_response, bins=bins)
        return classification

    def call_llm(self, prompt: str, llm: LLM) -> str:
        """Call LLM.

        Args:
            prompt (str): Prompt
            llm (LLM): LLM

        Returns:
            str: Classification
        """
        try:
            completion = llm.complete(prompt)[LLM.RESPONSE]
            classification: str = completion.text.strip()
            self.tool.stream_log(f"LLM response: {completion}", level=LogLevel.DEBUG)
            return classification
        except Exception as e:
            self.stream_error_and_exit(f"Error calling LLM: {e}")
            raise e

    def clean_llm_response(self, llm_response: str, bins: list[str]) -> str:
        """Cleans the response from the LLM.

        Performs a substring search to find the returned classification.
        Treats it as `unknown` if the classification is not clear
        from the output.

        Args:
            llm_response (str): Response from LLM to clean
            bins (list(str)): List of bins to classify the file into.

        Returns:
            str: Cleaned classification that matches one of the bins.
        """
        classification = ReservedBins.UNKNOWN
        cleaned_response = llm_response.strip().lower()
        bins = [bin.lower() for bin in bins]

        # Truncate llm_response to the first 100 words
        words = cleaned_response.split()
        truncated_response = " ".join(words[:100])

        # Count occurrences of each bin in the truncated text
        bin_counts = {
            bin: len(re.findall(r"\b" + re.escape(bin) + r"\b", truncated_response))
            for bin in bins
        }

        # Filter bins that have a count greater than 0
        matching_bins = [bin for bin, count in bin_counts.items() if count > 0]

        # Determine classification based on the number of matching bins
        if len(matching_bins) == 1:
            classification = matching_bins[0]
        else:
            self.stream_error_and_exit(
                f"Unable to deduce classified bin from possible values of "
                f"'{matching_bins}', moving file to '{ReservedBins.UNKNOWN}' "
                "folder instead.",
                bin_to_copy_to=ReservedBins.UNKNOWN,
            )
        return classification
