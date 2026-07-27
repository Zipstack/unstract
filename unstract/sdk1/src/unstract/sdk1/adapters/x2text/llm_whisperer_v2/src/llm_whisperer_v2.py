from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from unstract.sdk1.adapters.exceptions import ExtractorError
from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.dto import (
    TextExtractionMetadata,
    TextExtractionResult,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.constants import (
    ImageOutputConfig,
    OutputModes,
    WhispererConfig,
    WhispererEndpoint,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.dto import (
    WhispererRequestParams,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import LLMWhispererHelper
from unstract.sdk1.adapters.x2text.x2text_adapter import X2TextAdapter
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

if TYPE_CHECKING:
    import requests

logger = logging.getLogger(__name__)


class LLMWhispererV2(X2TextAdapter):
    def __init__(self, settings: dict[str, Any]) -> None:
        """Initialize the LLMWhispererV2 text extraction adapter.

        Args:
            settings: Configuration dictionary containing LLMWhispererV2 API settings
                     including API key, base URL, and other parameters.
        """
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

    @staticmethod
    def _validate_pdf_only(input_file_path: str) -> None:
        """Enforce the PDF-only constraint for image output mode (v1).

        The message is sourced from ``ImageOutputConfig`` so it stays identical
        to the UI-layer validation surfaced in ``adapter_processor_v2``.
        """
        if not ImageOutputConfig.is_pdf(input_file_path):
            raise ExtractorError(
                ImageOutputConfig.PDF_ONLY_ERROR,
                status_code=400,
            )

    def _process_image_mode(
        self,
        input_file_path: str,
        output_file_path: str | None,
        fs: FileStorage,
        tag: str | list[str] | None = None,
    ) -> TextExtractionResult:
        """Image output mode branch of ``process()``.

        Validates PDF-only input, delegates the submit/download/persist flow to
        the helper, and returns a ``TextExtractionResult`` whose ``page_images``
        metadata carries the per-page references. ``extracted_text`` is a short
        human-readable summary (never JSON / never image data): image mode has
        no OCR text, but a non-empty extract keeps the Prompt Studio extraction
        cache from re-submitting the remote conversion on a re-run and keeps the
        indexed document meaningful. The per-page references live in
        ``extraction_metadata.page_images`` — never inside ``extracted_text``.
        ``tag`` is forwarded for service-side usage reporting.
        """
        logger.info("Image mode: processing %s in image output mode", input_file_path)
        self._validate_pdf_only(input_file_path)
        whisper_hash, page_images = LLMWhispererHelper.get_page_images(
            config=self.config,
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            fs=fs,
            tag=tag,
        )
        summary = LLMWhispererHelper.build_image_output_summary(page_images)
        # Persist the summary to the extract file so the extraction is
        # cache-consistent (no re-submit on re-run). Skipped when no output
        # path was requested.
        if output_file_path:
            LLMWhispererHelper.write_image_output(
                fs=fs,
                output_file_path=output_file_path,
                summary=summary,
            )
        logger.info(
            "Image mode: returning %d page image reference(s) for %s",
            len(page_images),
            input_file_path,
        )
        return TextExtractionResult(
            extracted_text=summary,
            extraction_metadata=TextExtractionMetadata(
                whisper_hash=whisper_hash,
                page_images=page_images,
            ),
        )

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage | None = None,
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
        if fs is None:
            fs = FileStorage(provider=FileStorageProvider.LOCAL)

        # Branch on the configured output mode. Image mode routes to a dedicated
        # path (PDF-only); every other mode follows the unchanged text path.
        output_mode = self.config.get(
            WhispererConfig.OUTPUT_MODE, OutputModes.LAYOUT_PRESERVING.value
        )
        enable_highlight = kwargs.get(X2TextConstants.ENABLE_HIGHLIGHT, False)
        if output_mode == OutputModes.IMAGE.value:
            # Highlighting produces line-level source references over extracted
            # text; image mode yields no text, so the combination is rejected
            # explicitly rather than silently returning empty highlight data.
            if enable_highlight:
                raise ExtractorError(
                    "Highlighting is not supported in image output mode; disable "
                    "highlight or select a text output mode.",
                    status_code=400,
                )
            return self._process_image_mode(
                input_file_path,
                output_file_path,
                fs,
                tag=kwargs.get(X2TextConstants.TAGS),
            )

        logger.info(
            "HIGHLIGHT_DEBUG LLMWhispererV2.process: enable_highlight=%s",
            enable_highlight,
        )
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
            whisper_hash=response.get(X2TextConstants.WHISPER_HASH_V2, ""),
            line_metadata=response.get("line_metadata"),
        )

        return TextExtractionResult(
            extracted_text=LLMWhispererHelper.extract_text_from_response(
                output_file_path,
                response,
                fs=fs,
            ),
            extraction_metadata=metadata,
        )
