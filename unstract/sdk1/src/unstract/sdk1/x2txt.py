import io
from abc import ABCMeta
from typing import Any

import pdfplumber

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.x2text import adapters
from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from unstract.sdk1.adapters.x2text.llm_whisperer.src import LLMWhisperer
from unstract.sdk1.adapters.x2text.llm_whisperer.src.constants import WhispererConfig
from unstract.sdk1.adapters.x2text.x2text_adapter import X2TextAdapter
from unstract.sdk1.audit import Audit
from unstract.sdk1.constants import LogLevel, MimeType, ToolEnv
from unstract.sdk1.exceptions import X2TextError
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.utils.tool import ToolUtils


class X2Text(metaclass=ABCMeta):
    def __init__(
        self,
        tool: BaseTool,
        adapter_instance_id: str | None = None,
        usage_kwargs: dict[Any, Any] = {},
    ):
        self._tool = tool
        self._x2text_adapters = adapters
        self._adapter_instance_id = adapter_instance_id
        self._x2text_instance: X2TextAdapter = None
        self._usage_kwargs = usage_kwargs
        self._initialise()

    @property
    def x2text_instance(self):
        return self._x2text_instance

    def _initialise(self):
        if self._adapter_instance_id:
            self._x2text_instance = self._get_x2text()

    def _get_x2text(self) -> X2TextAdapter:
        try:
            if not self._adapter_instance_id:
                raise X2TextError("Adapter instance ID not set. Initialisation failed")

            x2text_config = PlatformHelper.get_adapter_config(
                self._tool, self._adapter_instance_id
            )

            x2text_adapter_id = x2text_config.get(Common.ADAPTER_ID)
            if x2text_adapter_id in self._x2text_adapters:
                x2text_adapter = self._x2text_adapters[x2text_adapter_id][
                    Common.METADATA
                ][Common.ADAPTER]
                x2text_metadata = x2text_config.get(Common.ADAPTER_METADATA)
                # Add x2text service host, port and platform_service_key
                x2text_metadata[X2TextConstants.X2TEXT_HOST] = self._tool.get_env_or_die(
                    X2TextConstants.X2TEXT_HOST
                )
                x2text_metadata[X2TextConstants.X2TEXT_PORT] = self._tool.get_env_or_die(
                    X2TextConstants.X2TEXT_PORT
                )

                if not PlatformHelper.is_public_adapter(adapter_id=self._adapter_instance_id):
                    x2text_metadata[X2TextConstants.PLATFORM_SERVICE_API_KEY] = (
                        self._tool.get_env_or_die(
                            X2TextConstants.PLATFORM_SERVICE_API_KEY
                        )
                    )

                self._x2text_instance = x2text_adapter(x2text_metadata)

                return self._x2text_instance

        except Exception as e:
            self._tool.stream_log(
                log=f"Unable to get x2text adapter {self._adapter_instance_id}: {e}",
                level=LogLevel.ERROR,
            )
            raise X2TextError(f"Error getting text extractor: {e}") from e

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
        **kwargs: dict[Any, Any],
    ) -> TextExtractionResult:
        mime_type = fs.mime_type(input_file_path)
        text_extraction_result: TextExtractionResult = None
        if mime_type == MimeType.TEXT:
            extracted_text = fs.read(path=input_file_path, mode="r", encoding="utf-8")
            text_extraction_result = TextExtractionResult(
                extracted_text=extracted_text, extraction_metadata=None
            )
        text_extraction_result = self._x2text_instance.process(
            input_file_path, output_file_path, fs, **kwargs
        )
        # The will be executed each and every time text extraction takes place
        self.push_usage_details(input_file_path, mime_type, fs=fs)
        return text_extraction_result

    def push_usage_details(
        self,
        input_file_path: str,
        mime_type: str,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> None:
        file_size = ToolUtils.get_file_size(input_file_path, fs)

        if mime_type == MimeType.PDF:
            pdf_contents = io.BytesIO(fs.read(path=input_file_path, mode="rb"))
            with pdfplumber.open(pdf_contents) as pdf:
                # calculate the number of pages
                page_count = len(pdf.pages)
            if isinstance(self._x2text_instance, LLMWhisperer):
                page_count = ToolUtils.calculate_page_count(
                    self._x2text_instance.config.get(WhispererConfig.PAGES_TO_EXTRACT),
                    page_count,
                )
            Audit().push_page_usage_data(
                platform_api_key=self._tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY),
                file_size=file_size,
                file_type=mime_type,
                page_count=page_count,
                kwargs=self._usage_kwargs,
            )
        else:
            # TODO: Calculate page usage for other file types (3000 words = 1 page)
            # We are allowing certain image types,and raw texts. We will consider them
            # as single page documents as there in no concept of page numbers.
            Audit().push_page_usage_data(
                platform_api_key=self._tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY),
                file_size=file_size,
                file_type=mime_type,
                page_count=1,
                kwargs=self._usage_kwargs,
            )
