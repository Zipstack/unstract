from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from unstract.sdk1.adapters.exceptions import ExtractorError
from unstract.sdk1.adapters.x2text.constants import (
    ImageOutputConstants,
    X2TextConstants,
)
from unstract.sdk1.adapters.x2text.dto import (
    TextExtractionMetadata,
    TextExtractionResult,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.constants import (
    ImageOutputConfig,
    Modes,
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
    from unstract.sdk1.utils.image_limits.policy import ImageModePolicy

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
    def get_doc_url() -> str:
        return "https://docs.unstract.com/unstract/unstract_platform/adapters/text_extractors/llm_whisperer_text_extractor_v2/"

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
            try:
                page_num = int(page_str)
            except (TypeError, ValueError):
                # Page keys come straight from the LLMWhisperer response;
                # skip anything non-numeric rather than failing the whole
                # extraction.
                logger.warning("DOC_INSIGHTS: skipping non-numeric page key %r", page_str)
                continue
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

    @staticmethod
    def _validate_pdf_only(input_file_path: str, fs: FileStorage | None = None) -> None:
        """Enforce the PDF-only constraint for image output mode (v1).

        Checks the filename extension first; when the storage name carries no
        ``.pdf`` suffix, falls back to content sniffing — workflow executions
        store the source file under an extension-less name (e.g. ``SOURCE``),
        so an extension-only check would false-reject every deployment input.
        Fail-closed: if the content cannot be verified either, reject.

        The message is sourced from ``ImageOutputConfig`` so it stays identical
        to the UI-layer validation surfaced in ``adapter_processor_v2``.
        """
        if ImageOutputConfig.is_pdf(input_file_path):
            return
        if fs is not None:
            try:
                header = fs.read(path=input_file_path, mode="rb", length=5)
            except Exception:
                header = b""
            if ImageOutputConstants.is_pdf_bytes(header):
                return
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
        image_limits: ImageModePolicy | None = None,
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
        ``tag`` is forwarded for service-side usage reporting; ``image_limits``
        (an ``ImageModePolicy`` for the consuming LLM, or None) drives the
        page-budget and size checks in the helper.
        """
        logger.info("Image mode: processing %s in image output mode", input_file_path)
        self._validate_pdf_only(input_file_path, fs=fs)
        whisper_hash, page_images = LLMWhispererHelper.get_page_images(
            config=self.config,
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            fs=fs,
            tag=tag,
            image_limits=image_limits,
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
            TextExtractionResult: Extracted text, metadata and, when
                LLMWhisperer reports it, the processed page count (None in
                image output mode).
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
                image_limits=kwargs.get(X2TextConstants.IMAGE_LIMITS),
            )

        logger.info(
            "HIGHLIGHT_DEBUG LLMWhispererV2.process: enable_highlight=%s",
            enable_highlight,
        )
        extra_params = WhispererRequestParams(
            tag=kwargs.get(X2TextConstants.TAGS),
            enable_highlight=enable_highlight,
        )
        response = LLMWhispererHelper.send_whisper_request(
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
            page_count=LLMWhispererHelper.get_processed_page_count(response),
        )
