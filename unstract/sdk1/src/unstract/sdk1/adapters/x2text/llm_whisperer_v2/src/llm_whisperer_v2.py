import logging
import os
from typing import Any

import requests

from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.dto import (
    TextExtractionMetadata,
    TextExtractionResult,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.constants import (
    WhispererEndpoint,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.dto import (
    WhispererRequestParams,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import LLMWhispererHelper
from unstract.sdk1.adapters.x2text.x2text_adapter import X2TextAdapter
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

logger = logging.getLogger(__name__)


class LLMWhispererV2(X2TextAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("LLMWhispererV2")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93"

    @staticmethod
    def get_name() -> str:
        return "LLMWhisperer V2"

    @staticmethod
    def get_description() -> str:
        return "LLMWhisperer V2 X2Text"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/LLMWhispererV2.png"

    def test_connection(self) -> bool:
        LLMWhispererHelper.test_connection_request(
            config=self.config,
            request_endpoint=WhispererEndpoint.TEST_CONNECTION,
        )
        return True

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
        **kwargs: dict[Any, Any],
    ) -> TextExtractionResult:
        """Used to extract text from documents.

        Args:
            input_file_path (str): Path to file that needs to be extracted
            output_file_path (Optional[str], optional): File path to write
                extracted text into, if None doesn't write to a file.
                Defaults to None.

        Returns:
            str: Extracted text
        """
        enable_highlight = kwargs.get(X2TextConstants.ENABLE_HIGHLIGHT, False)
        extra_params = WhispererRequestParams(
            tag=kwargs.get(X2TextConstants.TAGS),
            enable_highlight=enable_highlight,
        )
        response: requests.Response = LLMWhispererHelper.send_whisper_request(
            input_file_path=input_file_path,
            config=self.config,
            fs=fs,
            extra_params=extra_params,
        )
        metadata = TextExtractionMetadata(
            whisper_hash=response.get(X2TextConstants.WHISPER_HASH_V2, "")
        )

        return TextExtractionResult(
            extracted_text=LLMWhispererHelper.extract_text_from_response(
                output_file_path,
                response,
                fs=fs,
            ),
            extraction_metadata=metadata,
        )
