from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.dto import (
    TextExtractionMetadata,
    TextExtractionResult,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.constants import (
    Modes,
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

    @staticmethod
    def _index_first_content_line_per_page(
        line_metadata: list[list[int]],
    ) -> dict[int, int]:
        """Map each page to its first content-line index in ``line_metadata``.

        Marker/empty rows like ``[0, 0, 0, 3168]`` or ``[1, 0, 0, 0]`` are
        skipped because they have zero height or zero page_height and
        produce an invisible overlay (and divide-by-zero in the frontend's
        percentage calculation).
        """
        page_first_line: dict[int, int] = {}
        for idx, entry in enumerate(line_metadata):
            if not isinstance(entry, list) or len(entry) < 4:
                continue
            page, _y, height, page_height = entry[0], entry[1], entry[2], entry[3]
            if height <= 0 or page_height <= 0:
                continue
            if page not in page_first_line:
                page_first_line[page] = idx
        return page_first_line

    @staticmethod
    def _build_page_reference_entry(
        line_index: int,
        signatures: list[Any],
        line_metadata: list[list[int]],
    ) -> dict[str, Any]:
        """Build a single ``signature_page_references`` entry for one page."""
        coords_entry = line_metadata[line_index]
        coords = (
            list(coords_entry[:4])
            if isinstance(coords_entry, list) and len(coords_entry) >= 4
            else None
        )
        return {
            "hex": f"0x{line_index + 1:02X}",  # 1-indexed hex
            "line_metadata_index": line_index,
            "signers": [
                sig.get("name", "Unknown") for sig in signatures if isinstance(sig, dict)
            ],
            "coords": coords,
        }

    @staticmethod
    def _build_signature_page_references(
        signature_metadata: dict[str, list[Any]],
        line_metadata: list[list[int]],
    ) -> dict[str, Any] | None:
        """Build page references for frontend navigation to signature pages.

        For each page that has signatures, finds the first **content**
        line in ``line_metadata`` (skipping zero-height marker rows) and
        emits its 1-indexed hex value plus resolved coords. The frontend
        uses ``coords`` directly in its highlight overlay; the workers
        executor caches the result in a sidecar JSON next to the
        extracted text file so cached extracts retain it.

        Args:
            signature_metadata: Dict keyed by page number (str, 0-indexed)
                with lists of signature entries.
            line_metadata: List of [page, y_pos, height, page_height] arrays.

        Returns:
            Dict mapping page number to ``{hex, line_metadata_index,
            signers, coords}``, or None if no references could be built.
        """
        if not line_metadata:
            logger.warning(
                "DOC_INSIGHTS: no line_metadata available, "
                "cannot build page references"
            )
            return None

        page_first_line = LLMWhispererV2._index_first_content_line_per_page(line_metadata)
        logger.debug("DOC_INSIGHTS: page_first_line map: %s", page_first_line)

        references: dict[str, Any] = {}
        for page_str, signatures in signature_metadata.items():
            if not signatures:
                continue
            page_num = int(page_str)
            if page_num not in page_first_line:
                logger.warning(
                    "DOC_INSIGHTS: page %d not found in line_metadata", page_num
                )
                continue
            references[page_str] = LLMWhispererV2._build_page_reference_entry(
                line_index=page_first_line[page_num],
                signatures=signatures,
                line_metadata=line_metadata,
            )

        return references if references else None

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
        enable_highlight = kwargs.get(X2TextConstants.ENABLE_HIGHLIGHT, False)
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
        # Extract signature_metadata when using document_insights mode
        signature_metadata = None
        mode = self.config.get(WhispererConfig.MODE, Modes.FORM.value)
        logger.info(
            "DOC_INSIGHTS: mode=%s, is_document_insights=%s",
            mode,
            mode == Modes.DOCUMENT_INSIGHTS.value,
        )
        if mode == Modes.DOCUMENT_INSIGHTS.value:
            response_metadata = response.get("metadata", {})
            logger.info(
                "DOC_INSIGHTS: response has metadata keys: %s",
                list(response_metadata.keys()) if response_metadata else "None",
            )
            signature_metadata = {}
            for page_num, page_data in response_metadata.items():
                if isinstance(page_data, dict) and "signature_metadata" in page_data:
                    signature_metadata[page_num] = page_data["signature_metadata"]
                    logger.info(
                        "DOC_INSIGHTS: page %s has %d signature(s): %s",
                        page_num,
                        len(page_data["signature_metadata"]),
                        [s.get("name") for s in page_data["signature_metadata"]],
                    )
            if not any(signature_metadata.values()):
                logger.info("DOC_INSIGHTS: no signatures found across any page")
                signature_metadata = None
            else:
                logger.info(
                    "DOC_INSIGHTS: signature_metadata extracted for pages: %s",
                    list(signature_metadata.keys()),
                )

        # Compute signature page references for frontend navigation
        signature_page_references = None
        if signature_metadata:
            raw_line_metadata = response.get("line_metadata", [])
            logger.info(
                "DOC_INSIGHTS: line_metadata has %d entries, "
                "computing page references",
                len(raw_line_metadata),
            )
            signature_page_references = LLMWhispererV2._build_signature_page_references(
                signature_metadata, raw_line_metadata
            )
            logger.info(
                "DOC_INSIGHTS: signature_page_references=%s",
                signature_page_references,
            )

        metadata = TextExtractionMetadata(
            whisper_hash=response.get(X2TextConstants.WHISPER_HASH_V2, ""),
            line_metadata=response.get("line_metadata"),
            signature_metadata=signature_metadata,
            signature_page_references=signature_page_references,
        )

        return TextExtractionResult(
            extracted_text=LLMWhispererHelper.extract_text_from_response(
                output_file_path,
                response,
                fs=fs,
            ),
            extraction_metadata=metadata,
        )
