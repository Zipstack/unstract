import logging
import os
import pathlib
from typing import Any

from httpx import ConnectError
from llama_parse import LlamaParse

from unstract.sdk1.adapters.exceptions import AdapterError
from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from unstract.sdk1.adapters.x2text.llama_parse.src.constants import LlamaParseConfig
from unstract.sdk1.adapters.x2text.x2text_adapter import X2TextAdapter
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

logger = logging.getLogger(__name__)


class LlamaParseAdapter(X2TextAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("LlamaParse")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "llamaparse|78860239-b3cc-4cc5-b3de-f84315f75d14"

    @staticmethod
    def get_name() -> str:
        return "LlamaParse"

    @staticmethod
    def get_description() -> str:
        return "LlamaParse X2Text"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/llama-parse.png"

    def _call_parser(
        self,
        input_file_path: str,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> str:
        parser = LlamaParse(
            api_key=self.config.get(LlamaParseConfig.API_KEY),
            base_url=self.config.get(LlamaParseConfig.BASE_URL),
            result_type=self.config.get(LlamaParseConfig.RESULT_TYPE),
            verbose=self.config.get(LlamaParseConfig.VERBOSE),
            language="en",
            ignore_errors=False,
        )

        try:
            file_extension = pathlib.Path(input_file_path).suffix
            if not file_extension:
                try:
                    input_file_extension = fs.guess_extension(input_file_path)
                    input_file_path_copy = input_file_path
                    input_file_path = ".".join(
                        (input_file_path_copy, input_file_extension)
                    )
                    text_content = fs.read(
                        path=input_file_path_copy, mode="rb", encoding="utf-8"
                    )
                    fs.write(
                        path=input_file_path,
                        data=text_content,
                        mode="wb",
                        encoding="utf-8",
                    )
                except OSError as os_err:
                    logger.error("Exception raised while handling input file.")
                    raise AdapterError(str(os_err))

            file_bytes = fs.read(path=input_file_path, mode="rb")
            documents = parser.load_data(
                file_bytes, extra_info={"file_name": input_file_path}
            )

        except ConnectError as connec_err:
            logger.error(f"Invalid Base URL given. : {connec_err}")
            raise AdapterError(
                "Unable to connect to llama-parse`s service, " "please check the Base URL"
            )
        except Exception as exe:
            logger.error(
                "Seems like an invalid API Key or possible internal errors: {exe}"
            )
            raise AdapterError(str(exe))

        response_text = documents[0].text
        return response_text  # type:ignore

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
        **kwargs: dict[Any, Any],
    ) -> TextExtractionResult:
        response_text = self._call_parser(input_file_path=input_file_path, fs=fs)
        if output_file_path:
            fs.write(
                path=output_file_path,
                mode="w",
                encoding="utf-8",
                data=response_text,
            )

        return TextExtractionResult(extracted_text=response_text)

    def test_connection(self) -> bool:
        self._call_parser(
            input_file_path=f"{os.path.dirname(__file__)}/static/test_input.doc"
        )
        return True
