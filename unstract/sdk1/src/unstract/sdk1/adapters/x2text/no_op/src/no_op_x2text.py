import logging
import os
import time
from typing import Any

from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from unstract.sdk1.adapters.x2text.x2text_adapter import X2TextAdapter
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

logger = logging.getLogger(__name__)


class NoOpX2Text(X2TextAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("NoOpX2Text")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "noOpX2text|mp66d1op-7100-d340-9101-846fc7115676"

    @staticmethod
    def get_name() -> str:
        return "No Op X2Text"

    @staticmethod
    def get_description() -> str:
        return "No Op X2Text Adapter"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/noOpx2Text.png"

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
        **kwargs: dict[Any, Any],
    ) -> TextExtractionResult:
        extracted_text: str = (
            "This is a No Op x2text adapter response."
            " This is a sample response and intended for testing \f"
        )
        time.sleep(self.config.get("wait_time"))
        if output_file_path:
            fs.write(
                path=output_file_path, mode="w", data=extracted_text, encoding="utf-8"
            )
        return TextExtractionResult(extracted_text=extracted_text)

    def test_connection(self) -> bool:
        time.sleep(self.config.get("wait_time"))
        return True
