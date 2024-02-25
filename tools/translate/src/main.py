import io
import json
import sys
from pathlib import Path
from typing import Any

from constants import EnvKey, GoogleTranslateKey, StaticData
from google.auth.transport import requests as google_requests
from google.cloud import translate_v2 as translate  # type: ignore
from google.oauth2.service_account import Credentials
from unstract.sdk.cache import ToolCache
from unstract.sdk.constants import LogState, MetadataKey, ToolEnv
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint
from unstract.sdk.utils import ToolUtils
from unstructured.partition.auto import partition


class UnstractTranslate(BaseTool):
    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        target_language = settings["targetLanguage"].lower()
        processor = settings["processor"]

        if target_language not in StaticData.LANGUAGE_CODES:
            self.stream_error_and_exit(
                f"Target language not found: {target_language}"
            )

        if processor not in StaticData.SUPPORTED_PROCESSORS:
            self.stream_error_and_exit(
                f"Processor not supported yet: {processor}"
            )

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        language_codes = StaticData.LANGUAGE_CODES
        target_language = settings["targetLanguage"].lower()
        processor = settings["processor"]
        use_cache = settings["useCache"]

        self.stream_log("Reading file...")
        text = self._extract_text(input_file)
        self.stream_log(f"Text length: {len(text)}")

        # Update GUI
        input_text_for_log = text
        if len(input_text_for_log) > 500:
            input_text_for_log = input_text_for_log[:500] + "...(truncated)"
        input_log = (
            f"Target language: `{target_language}`\n\nInput text:\n\n"
            f"```text\n{input_text_for_log}\n```\n\n"
        )
        output_log = ""
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        cache_key = (
            f"cache:{self.workflow_id}:{processor}:"
            f"{language_codes[target_language]}:"
            f"{ToolUtils.hash_str(text)}"
        )
        translated_text = ""
        cost_value = 0.0
        cost_unit = ""
        cache = None
        is_cache_data_available = False
        if use_cache:  # Get the data from cache
            self.stream_log("Trying to retrieve cached data")
            cache = ToolCache(
                tool=self,
                platform_host=self.get_env_or_die(ToolEnv.PLATFORM_HOST),
                platform_port=int(self.get_env_or_die(ToolEnv.PLATFORM_PORT)),
            )
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                translated_text = cached_response
                cost_unit = "cache"
                is_cache_data_available = True
            else:
                self.stream_log("Cache data not available")

        # Follow the usual steps, since cache is disabled
        if not translated_text:
            if processor == GoogleTranslateKey.PROCESSOR:
                google_service_account: str = self.get_env_or_die(
                    EnvKey.GOOGLE_SERVICE_ACCOUNT
                )
                credentials = Credentials.from_service_account_info(
                    json.loads(google_service_account),
                    scopes=GoogleTranslateKey.CREDENTIAL_SCOPES,
                )
                credentials.refresh(google_requests.Request())
                translate_client = translate.Client(credentials=credentials)

                # Text can also be a sequence of strings, in which case
                # this method will return a sequence of results for each text.
                self.stream_log("Sending text to Google Translate")
                result = translate_client.translate(
                    text, target_language=language_codes[target_language]
                )
                self.stream_log("Received text from Google Translate")

                if result is not None and "translatedText" in result:
                    translated_text = result["translatedText"]
                cost_value = len(text)
                cost_unit = "google_translate"
            else:
                self.stream_error_and_exit(
                    f"Unsupported processor: {processor}"
                )

        if use_cache and cache is not None and not is_cache_data_available:
            cache.set(cache_key, translated_text)

        output_log = (
            f"### Translated text\n\n```text\n{translated_text}\n```\n\n"
        )
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        # Write the translated text to output file
        try:
            self.stream_log("Writing tool output")
            source_name = self.get_exec_metadata.get(MetadataKey.SOURCE_NAME)
            output_path = Path(output_dir) / f"{Path(source_name).stem}.txt"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated_text)
        except Exception as e:
            self.stream_error_and_exit(f"Error creating output file: {e}")

        self.stream_cost(cost_value, cost_unit)
        self.write_tool_result(data=translated_text)

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
    tool = UnstractTranslate.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
