import io
import json
import sys
from pathlib import Path
from typing import Any

import nanoid
import requests
from doc_pii_redactor.constants import DocProcessorConstants, EnvKey
from doc_pii_redactor.enums import Processor
from doc_pii_redactor.helper import PIIRedactHelper
from unstract.sdk.cache import ToolCache
from unstract.sdk.constants import LogState, MetadataKey, ToolEnv
from unstract.sdk.platform import PlatformHelper
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint
from unstructured.partition.auto import partition


class UnstractDocPIIRedactor(BaseTool):
    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        processor = settings["processor"]
        allowed_processors = [Processor.AMAZON_COMPREHEND.value]
        if processor not in allowed_processors:
            self.stream_error_and_exit(
                f"Invalid processor. Only {allowed_processors} is allowed"
            )

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        processor = settings["processor"]
        redact_items = settings["redactionElements"]
        use_cache = settings["useCache"]
        score_threshold = settings["scoreThreshold"]
        # Timeout set to 10mins, configure as necessary
        doc_processor_timeout = DocProcessorConstants.REQUEST_TIMEOUT

        pii_redact_helper = PIIRedactHelper(self)

        self.stream_log("Reading file...")
        text = self._extract_text(input_file)
        self.stream_log(f"Text length: {len(text)}")

        # Update GUI
        input_text_for_log = text
        if len(input_text_for_log) > 500:
            input_text_for_log = input_text_for_log[:500] + "...(truncated)"
        input_log = (
            f"Items to redact: `{redact_items}`\n\nInput text:\n\n"
            f"```text\n{input_text_for_log}\n```\n\n"
        )
        output_log = ""
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        entities_to_redact = None
        if use_cache:
            self.stream_log("Trying to retrieve from cache")
            cache_key = pii_redact_helper.get_cache_key(
                workflow_id=self.workflow_id, settings=settings, input_text=text
            )
            cache = ToolCache(
                tool=self,
                platform_host=self.get_env_or_die(ToolEnv.PLATFORM_HOST),
                platform_port=int(self.get_env_or_die(ToolEnv.PLATFORM_PORT)),
            )
            items_to_redact_str = cache.get(cache_key)
            if items_to_redact_str:
                entities_to_redact = json.loads(items_to_redact_str)
                self.stream_cost(cost=0.0, cost_units="cache")

        if not entities_to_redact:
            entities_to_redact = pii_redact_helper.detect_pii_entities(
                text, processor, redact_items, score_threshold
            )
            cost_units = 0.0
            cost_type = "free"
            if processor == Processor.AMAZON_COMPREHEND.value:
                cost_type = "amazon_comprehend_units"
                cost_units = len(text) / 100.0
                if cost_units < 3.0:
                    cost_units = 3.0
            self.stream_cost(cost_units, cost_type)

        if use_cache and cache:
            cache.set(cache_key, json.dumps(entities_to_redact))

        self.stream_log(f"Entities to redact: {entities_to_redact}")

        output_log = (
            f"### Entities to redact\n\n```text\n{entities_to_redact}\n```\n\n"
        )
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        find_and_replace = {}
        for item in entities_to_redact:
            find_and_replace[item] = PIIRedactHelper.create_redaction_overlay(
                item
            )

        # Upload the file to the document processor
        document_processor_url = self.get_env_or_die(EnvKey.DOC_PROCESSOR_URL)
        document_processor_api_key = self.get_env_or_die(
            EnvKey.DOC_PROCESSOR_API_KEY
        )
        self.stream_log(f"Document processor URL: {document_processor_url}")
        self.stream_log("Uploading file to document processor")
        with open(input_file, "rb") as file:
            files = {"file": file}
            platform_helper = PlatformHelper(
                tool=self,
                platform_host=self.get_env_or_die(ToolEnv.PLATFORM_HOST),
                platform_port=int(self.get_env_or_die(ToolEnv.PLATFORM_PORT)),
            )
            platform_details = platform_helper.get_platform_details()
            if not platform_details:
                # Errors are logged by the SDK itself
                exit(1)
            account_id = platform_details.get("organization_id")

            file_name = nanoid.generate()
            url = (
                f"{document_processor_url}/upload?account_id={account_id}"
                f"&file_name={file_name}"
            )
            response = requests.post(
                url,
                files=files,
                headers={"Authorization": f"{document_processor_api_key}"},
                timeout=doc_processor_timeout,
            )
            if response.status_code != 200:
                self.stream_error_and_exit(
                    "Error uploading file to document "
                    f"processor: {response.status_code}"
                )
        self.stream_log("File uploaded to document processor")

        # Now perform the find and replace
        self.stream_log("Performing find and replace")
        url = (
            f"{document_processor_url}/find_and_replace?account_id={account_id}"
            f"&file_name={file_name}&output_format=pdf"
        )
        # The returned value from the document processor is a file
        self.stream_log(f"Find and replace: {find_and_replace}")
        response = requests.post(
            url,
            headers={
                "Authorization": f"{document_processor_api_key}",
                "Content-Type": "application/json",
            },
            json=find_and_replace,
            timeout=doc_processor_timeout,
        )
        if response.status_code != 200:
            self.stream_error_and_exit(
                f"Error performing find and replace: {response.status_code}"
            )

        redacted_text = response.content
        # Write the redacted text to output file
        try:
            self.stream_log("Writing tool output")
            source_name = self.get_exec_metadata.get(MetadataKey.SOURCE_NAME)
            output_path = Path(output_dir) / source_name
            with open(output_path, "wb") as f:
                f.write(redacted_text)
        except Exception as e:
            self.stream_error_and_exit(f"Error creating output file: {e}")

        self.write_tool_result(data="PII redacted successfully")

    def _extract_text(self, file: str) -> str:
        """Extract text from file.

        Args:
            file (str): The path to the input file

        Returns:
            str: page content
        """
        try:
            with open(file, mode="rb") as input_file_obj:
                bytes_io = io.BytesIO(input_file_obj.read())
                elements = partition(file=bytes_io)
        except Exception as e:
            self.stream_error_and_exit(f"Error partitioning file: {e}")
        text = "\n\n".join([str(el) for el in elements])
        return text


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = UnstractDocPIIRedactor.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
