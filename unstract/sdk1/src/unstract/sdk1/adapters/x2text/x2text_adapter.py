from abc import ABC
from typing import Any

from unstract.sdk1.adapters.base import Adapter
from unstract.sdk1.adapters.enums import AdapterTypes
from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider


class X2TextAdapter(Adapter, ABC):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_id() -> str:
        return ""

    @staticmethod
    def get_name() -> str:
        return ""

    @staticmethod
    def get_description() -> str:
        return ""

    @staticmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.X2TEXT

    def test_connection(self) -> bool:
        return False

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
        **kwargs: dict[Any, Any],
    ) -> TextExtractionResult:
        return TextExtractionResult(
            extracted_text="extracted text", extraction_metadata=None
        )
