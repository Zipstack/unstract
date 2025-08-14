import logging
import os
from typing import Any

from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from unstract.sdk1.adapters.x2text.helper import UnstructuredHelper
from unstract.sdk1.adapters.x2text.x2text_adapter import X2TextAdapter
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

logger = logging.getLogger(__name__)


class UnstructuredCommunity(X2TextAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("UnstructuredIOCommunity")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "unstructuredcommunity|eeed506f-1875-457f-9101-846fc7115676"

    @staticmethod
    def get_name() -> str:
        return "Unstructured IO Community"

    @staticmethod
    def get_description() -> str:
        return "Unstructured IO Community X2Text"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/UnstructuredIO.png"

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
        **kwargs: dict[Any, Any],
    ) -> TextExtractionResult:
        extracted_text: str = UnstructuredHelper.process_document(
            self.config, input_file_path, output_file_path, fs
        )

        return TextExtractionResult(extracted_text=extracted_text)

    def test_connection(self) -> bool:
        result: bool = UnstructuredHelper.test_server_connection(self.config)
        return result
