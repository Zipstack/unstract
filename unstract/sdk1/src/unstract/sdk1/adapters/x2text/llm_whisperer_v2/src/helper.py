import json
import logging
import re
import time
import zipfile
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from requests import Response
from requests.exceptions import ConnectionError, HTTPError, Timeout
from unstract.llmwhisperer.client_v2 import (
    LLMWhispererClientException,
    LLMWhispererClientV2,
)
from unstract.sdk1.adapters.exceptions import ExtractorError
from unstract.sdk1.adapters.utils import AdapterUtils
from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.dto import PageImageReference
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.constants import (
    ImageOutputConfig,
    Modes,
    OutputModes,
    WhispererConfig,
    WhispererDefaults,
    WhispererEndpoint,
    WhispererHeader,
    WhisperStatus,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.dto import (
    WhispererRequestParams,
)
from unstract.sdk1.constants import MimeType
from unstract.sdk1.exceptions import FileOperationError
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider
from unstract.sdk1.utils.retry_utils import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


class LLMWhispererHelper:
    @staticmethod
    def get_request_headers(config: dict[str, Any]) -> dict[str, Any]:
        """Obtains the request headers to authenticate with LLMWhisperer.

        Returns:
            str: Request headers
        """
        return {
            "accept": MimeType.JSON,
            WhispererHeader.UNSTRACT_KEY: config.get(WhispererConfig.UNSTRACT_KEY),
        }

    @staticmethod
    def _send_raw_request(
        config: dict[str, Any],
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        data: BytesIO | None = None,
        headers: dict[str, Any] | None = None,
        timeout: float = WhispererDefaults.IMAGE_REQUEST_TIMEOUT,
        stream: bool = False,
    ) -> Response:
        """Single outbound raw-``requests`` code path for the adapter (UNS-743).

        Resolves the service base URL and auth headers from ``config`` so that
        no caller constructs URLs or headers itself, issues the request with an
        explicit timeout, and maps transport / HTTP failures to ``ExtractorError``
        with the same semantics used across the adapter. Both ``test_connection``
        and the ``pdf-to-images`` image-mode calls go through here.
        """
        llm_whisperer_svc_url = f"{config.get(WhispererConfig.URL)}/api/v2"
        url = f"{llm_whisperer_svc_url}/{endpoint}"
        if headers is None:
            headers = LLMWhispererHelper.get_request_headers(config=config)
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                timeout=timeout,
                stream=stream,
            )
            response.raise_for_status()
            return response
        except ConnectionError as e:
            logger.error(f"Adapter error: {e}")
            raise ExtractorError(
                "Unable to connect to LLMWhisperer service, please check the URL",
                actual_err=e,
                status_code=503,
            ) from e
        except Timeout as e:
            msg = "Request to LLMWhisperer has timed out"
            logger.error(f"{msg}: {e}")
            raise ExtractorError(msg, actual_err=e, status_code=504) from e
        except HTTPError as e:
            logger.error(f"Adapter error: {e}")
            default_err = "Error while calling the LLMWhisperer service"
            msg = AdapterUtils.get_msg_from_request_exc(
                err=e, message_key="message", default_err=default_err
            )
            raise ExtractorError(
                msg, status_code=e.response.status_code, actual_err=e
            ) from e

    @staticmethod
    def test_connection_request(
        config: dict[str, Any], request_endpoint: str
    ) -> Response:
        return LLMWhispererHelper._send_raw_request(
            config=config,
            method="GET",
            endpoint=request_endpoint,
        )

    @staticmethod
    def make_request(
        config: dict[str, Any],
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        data: BytesIO | None = None,
        type: str = "whisper",
    ) -> Response:
        """Makes a request to LLMWhisperer service.

        Args:
            config (dict[str, Any]): LLMWhisperer config to use
            headers (Optional[dict[str, Any]], optional): Headers to pass.
                Defaults to None.
            params (Optional[dict[str, Any]], optional): Query params to pass.
                Defaults to None.
            data (Optional[BytesIO], optional): Data to pass in case of POST.
                Defaults to None.
            type (str, optional): Type of request / endpoint in LLMWhisperer.
                Defaults to "whisper".

        Returns:
            Response: Response from the request
        """
        llm_whisperer_svc_url = f"{config.get(WhispererConfig.URL)}/api/v2"
        if not headers:
            headers = LLMWhispererHelper.get_request_headers(config=config)

        try:
            response: dict[str, Any]
            client = LLMWhispererClientV2(
                base_url=llm_whisperer_svc_url,
                api_key=config.get(WhispererConfig.UNSTRACT_KEY),
                logging_level=WhispererDefaults.LOGGING_LEVEL,
                max_retries=WhispererDefaults.MAX_RETRIES,
                retry_min_wait=WhispererDefaults.RETRY_MIN_WAIT,
                retry_max_wait=WhispererDefaults.RETRY_MAX_WAIT,
            )
            if type == "whisper":
                response = client.whisper(**params, stream=data)
                whisper_hash = response.get(X2TextConstants.WHISPER_HASH_V2, "")
                if whisper_hash:
                    logger.info(f"LLMWhisperer responded, whisper_hash: {whisper_hash}")
                if response["status_code"] == 200:
                    response["extraction"][X2TextConstants.WHISPER_HASH_V2] = (
                        response.get(X2TextConstants.WHISPER_HASH_V2, "")
                    )
                    return response["extraction"]
                else:
                    response["message"] += (
                        ". Whisper hash: "
                        f"{response.get(X2TextConstants.WHISPER_HASH_V2, '')}"
                    )
                    raise ExtractorError(
                        response["message"],
                        response["status_code"],
                        actual_err=response,
                    )
            elif type == "highlight":
                response = client.get_highlight_data(**params)
                return response

        except ConnectionError as e:
            logger.error(f"Adapter error: {e}")
            raise ExtractorError(
                "Unable to connect to LLMWhisperer service, please check the URL",
                actual_err=e,
                status_code=503,
            ) from e
        except Timeout as e:
            msg = "Request to LLMWhisperer has timed out"
            logger.error(f"{msg}: {e}")
            raise ExtractorError(msg, actual_err=e, status_code=504) from e
        except LLMWhispererClientException as e:
            logger.error(f"LLM Whisperer error: {e}")
            raise ExtractorError(
                message=f"LLM Whisperer error: {e}",
                actual_err=e,
                status_code=500,
            ) from e

        return response

    @staticmethod
    def get_whisperer_params(
        config: dict[str, Any], extra_params: WhispererRequestParams
    ) -> dict[str, Any]:
        """Gets query params meant for /whisper endpoint.

        The params is filled based on the configuration passed.

        Returns:
            dict[str, Any]: Query params
        """
        params = {
            WhispererConfig.MODE: config.get(WhispererConfig.MODE, Modes.FORM.value),
            WhispererConfig.OUTPUT_MODE: config.get(
                WhispererConfig.OUTPUT_MODE, OutputModes.LAYOUT_PRESERVING.value
            ),
            WhispererConfig.LINE_SPLITTER_TOLERANCE: config.get(
                WhispererConfig.LINE_SPLITTER_TOLERANCE,
                WhispererDefaults.LINE_SPLITTER_TOLERANCE,
            ),
            WhispererConfig.LINE_SPLITTER_STRATEGY: config.get(
                WhispererConfig.LINE_SPLITTER_STRATEGY,
                WhispererDefaults.LINE_SPLITTER_STRATEGY,
            ),
            WhispererConfig.HORIZONTAL_STRETCH_FACTOR: config.get(
                WhispererConfig.HORIZONTAL_STRETCH_FACTOR,
                WhispererDefaults.HORIZONTAL_STRETCH_FACTOR,
            ),
            WhispererConfig.PAGES_TO_EXTRACT: config.get(
                WhispererConfig.PAGES_TO_EXTRACT,
                WhispererDefaults.PAGES_TO_EXTRACT,
            ),
            WhispererConfig.MARK_VERTICAL_LINES: config.get(
                WhispererConfig.MARK_VERTICAL_LINES,
                WhispererDefaults.MARK_VERTICAL_LINES,
            ),
            WhispererConfig.MARK_HORIZONTAL_LINES: config.get(
                WhispererConfig.MARK_HORIZONTAL_LINES,
                WhispererDefaults.MARK_HORIZONTAL_LINES,
            ),
            WhispererConfig.PAGE_SEPARATOR: config.get(
                WhispererConfig.PAGE_SEPARATOR,
                WhispererDefaults.PAGE_SEPARATOR,
            ),
            WhispererConfig.ADD_LINE_NOS: extra_params.enable_highlight,
            WhispererConfig.INCLUDE_LINE_CONFIDENCE: extra_params.enable_highlight,
        }
        logger.info(
            "HIGHLIGHT_DEBUG whisper params: ADD_LINE_NOS=%s",
            params.get(WhispererConfig.ADD_LINE_NOS),
        )
        params.update(
            {
                # Not providing default value to maintain legacy compatablity
                # these are optional params and identifiers for audit
                WhispererConfig.TAG: extra_params.tag
                or config.get(
                    WhispererConfig.TAG,
                    WhispererDefaults.TAG,
                ),
                WhispererConfig.USE_WEBHOOK: config.get(WhispererConfig.USE_WEBHOOK, ""),
                WhispererConfig.WEBHOOK_METADATA: config.get(
                    WhispererConfig.WEBHOOK_METADATA
                ),
                WhispererConfig.WAIT_TIMEOUT: config.get(
                    WhispererConfig.WAIT_TIMEOUT,
                    WhispererDefaults.WAIT_TIMEOUT,
                ),
                WhispererConfig.WAIT_FOR_COMPLETION: (
                    WhispererDefaults.WAIT_FOR_COMPLETION
                ),
            }
        )
        if params[WhispererConfig.MODE] == Modes.LOW_COST.value:
            params.update(
                {
                    WhispererConfig.MEDIAN_FILTER_SIZE: config.get(
                        WhispererConfig.MEDIAN_FILTER_SIZE,
                        WhispererDefaults.MEDIAN_FILTER_SIZE,
                    ),
                    WhispererConfig.GAUSSIAN_BLUR_RADIUS: config.get(
                        WhispererConfig.GAUSSIAN_BLUR_RADIUS,
                        WhispererDefaults.GAUSSIAN_BLUR_RADIUS,
                    ),
                }
            )
        return params

    @staticmethod
    def send_whisper_request(
        input_file_path: str,
        config: dict[str, Any],
        extra_params: WhispererRequestParams,
        fs: FileStorage | None = None,
    ) -> requests.Response:
        if fs is None:
            fs = FileStorage(provider=FileStorageProvider.LOCAL)
        params = LLMWhispererHelper.get_whisperer_params(
            config=config, extra_params=extra_params
        )
        response: requests.Response
        try:
            input_file_data = BytesIO(fs.read(path=input_file_path, mode="rb"))
            enable_highlight = extra_params.enable_highlight
            response = LLMWhispererHelper.make_request(
                config=config,
                params=params,
                data=input_file_data,
            )
            if enable_highlight:
                whisper_hash = response.get(X2TextConstants.WHISPER_HASH_V2, "")
                highlight_data = LLMWhispererHelper.make_highlight_data_request(
                    config,
                    whisper_hash,
                    enable_highlight,
                )
                response["line_metadata"] = highlight_data
        except OSError as e:
            logger.error(f"OS error while reading {input_file_path}: {e}")
            raise ExtractorError(str(e)) from e
        return response

    @staticmethod
    def make_highlight_data_request(
        config: dict[str, Any], whisper_hash: str, enable_highlight: bool
    ) -> dict[Any, Any]:
        """Makes a call to get highlight data from LLMWhisperer.

        Args:
            config (dict[str, Any]): LLMWhisperer config to use
            whisper_hash (str): Identifier of the extraction
            enable_highlight (bool): Whether to enable highlight

        Returns:
            dict[Any, Any]: Highlight data
        """
        logger.info(f"Extracting async for whisper hash: {whisper_hash}")

        headers: dict[str, Any] = LLMWhispererHelper.get_request_headers(config)
        params = {
            WhisperStatus.WHISPER_HASH: whisper_hash,
            WhispererConfig.EXTRACT_ALL_LINES: enable_highlight,
            WhispererConfig.LINES: "",
        }

        retrieve_response = LLMWhispererHelper.make_request(
            config=config,
            headers=headers,
            params=params,
            type="highlight",
        )
        return retrieve_response

    @staticmethod
    def extract_text_from_response(
        output_file_path: str | None,
        response: dict[str, Any],
        fs: FileStorage | None = None,
    ) -> str:
        if fs is None:
            fs = FileStorage(provider=FileStorageProvider.LOCAL)
        if not response:
            raise ExtractorError("Couldn't extract text from file", status_code=500)
        output_json = {}
        output_json = response
        if output_file_path:
            LLMWhispererHelper.write_output_to_file(
                output_json=output_json,
                output_file_path=Path(output_file_path),
                fs=fs,
            )
        return output_json.get("result_text", "")

    @staticmethod
    def write_output_to_file(
        output_json: dict,
        output_file_path: Path,
        fs: FileStorage | None = None,
    ) -> None:
        """Write LLMW outputs to file.

        Writes the extracted text and metadata to the specified output file
        and metadata file.

        Args:
            output_json (dict): The dictionary containing the extracted data,
                with "text" as the key for the main content.
            output_file_path (Path): The file path where the extracted text
                should be written.
            fs (FileStorage): File storage instance to use for writing

        Raises:
            ExtractorError: If there is an error while writing the output file.
        """
        if fs is None:
            fs = FileStorage(provider=FileStorageProvider.LOCAL)
        try:
            text_output = output_json.get("result_text", "")
            logger.info(f"Writing output to {output_file_path}")
            fs.write(
                path=str(output_file_path),
                mode="w",
                data=text_output,
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Error while writing {output_file_path}: {e}")
            raise ExtractorError(str(e)) from e
        try:
            # Define the directory of the output file and metadata paths
            output_dir = output_file_path.parent
            metadata_dir = output_dir / "metadata"
            metadata_file_name = output_file_path.with_suffix(".json").name
            metadata_file_path = metadata_dir / metadata_file_name
            # Ensure the metadata directory exists
            fs.mkdir(create_parents=True, path=str(metadata_dir))
            # Remove the "result_text" key from the metadata
            metadata = {
                key: value for key, value in output_json.items() if key != "result_text"
            }
            metadata_json = json.dumps(metadata, ensure_ascii=False, indent=4)
            logger.info(f"Writing metadata to {metadata_file_path}")
            fs.write(
                path=str(metadata_file_path),
                mode="w",
                data=metadata_json,
                encoding="utf-8",
            )
        except Exception as e:
            logger.warn(f"Error while writing metadata to {metadata_file_path}: {e}")

    # ------------------------------------------------------------------ #
    # Image output mode (pdf-to-images).                                  #
    #                                                                     #
    # These call the LLMWhisperer `pdf-to-images` endpoints via raw       #
    # `requests` (decision 2A). The exact endpoint/response contract is   #
    # centralised in ImageOutputConfig — see its docstring; it is an      #
    # ASSUMED contract (Service PR #647 is not available in this repo)    #
    # and is the single place to reconcile once the real API is known.    #
    # ------------------------------------------------------------------ #

    # Matches service page files like `page_001.png` / `page-1.png`. The
    # captured digits are passed through int() (leading zeros stripped there),
    # so no separate `0*` prefix is needed — keeping the pattern linear.
    _PAGE_IMAGE_RE = re.compile(r"page[_-]?(\d+)\.png$", re.IGNORECASE)

    @staticmethod
    def _safe_json(response: Response) -> dict[str, Any]:
        """Parse a JSON object body, tolerating non-JSON / non-object bodies."""
        try:
            parsed = response.json()
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def submit_pdf_to_images(
        config: dict[str, Any],
        file_data: BytesIO,
        tag: str | list[str] | None = None,
        file_name: str | None = None,
    ) -> str:
        """Submit a ``pdf-to-images`` job; returns the job id (whisper_hash).

        The image ``format``, ``tag`` (usage-report label) and ``file_name`` are
        sent as query params — consistent with the ``/whisper`` endpoint so the
        service attributes usage correctly (verified against Service PR #536).
        ``tag`` falls back to the adapter config, then the default.
        """
        resolved_tag = WhispererRequestParams(tag=tag).tag or config.get(
            WhispererConfig.TAG, WhispererDefaults.TAG
        )
        params: dict[str, Any] = {
            ImageOutputConfig.IMAGE_FORMAT_PARAM: ImageOutputConfig.DEFAULT_IMAGE_FORMAT,
            WhispererConfig.TAG: resolved_tag,
        }
        if file_name:
            params[ImageOutputConfig.FILE_NAME_PARAM] = file_name
        response = LLMWhispererHelper._send_raw_request(
            config=config,
            method="POST",
            endpoint=WhispererEndpoint.PDF_TO_IMAGES,
            params=params,
            data=file_data,
            timeout=WhispererDefaults.IMAGE_REQUEST_TIMEOUT,
        )
        body = LLMWhispererHelper._safe_json(response)
        whisper_hash = body.get(X2TextConstants.WHISPER_HASH_V2, "")
        if not whisper_hash:
            raise ExtractorError(
                "LLMWhisperer pdf-to-images submit did not return a job id "
                f"(whisper_hash). Response: {body}",
                status_code=502,
            )
        logger.info("Image mode: submitted pdf-to-images job %s", whisper_hash)
        return whisper_hash

    @staticmethod
    def poll_pdf_to_images_status(
        config: dict[str, Any], whisper_hash: str
    ) -> dict[str, Any]:
        """Poll the status endpoint until a terminal state is reached.

        Returns the terminal status payload on success (``status`` reaches
        ``PROCESSED``); raises ``ExtractorError`` on a failed/unknown state or
        once the poll budget is exhausted. Mirrors the submit-then-poll pattern
        already used for text extraction.
        """
        headers = LLMWhispererHelper.get_request_headers(config)
        params = {WhisperStatus.WHISPER_HASH: whisper_hash}
        for attempt in range(WhispererDefaults.IMAGE_POLL_MAX_ATTEMPTS):
            response = LLMWhispererHelper._send_raw_request(
                config=config,
                method="GET",
                endpoint=WhispererEndpoint.PDF_TO_IMAGES_STATUS,
                params=params,
                headers=headers,
                timeout=WhispererDefaults.IMAGE_REQUEST_TIMEOUT,
            )
            body = LLMWhispererHelper._safe_json(response)
            status = str(body.get(ImageOutputConfig.STATUS, "")).lower()
            logger.info(
                "Image mode: job %s status=%s (attempt %d/%d)",
                whisper_hash,
                status,
                attempt + 1,
                WhispererDefaults.IMAGE_POLL_MAX_ATTEMPTS,
            )
            if status in ImageOutputConfig.STATUS_SUCCESS:
                return body
            if status in ImageOutputConfig.STATUS_FAILURE:
                msg = body.get(ImageOutputConfig.MESSAGE, "unknown error")
                raise ExtractorError(
                    f"LLMWhisperer pdf-to-images job {whisper_hash} failed: {msg}",
                    status_code=500,
                )
            # Intermediate states (processing / queued / empty) -> keep polling.
            time.sleep(WhispererDefaults.IMAGE_POLL_INTERVAL)
        raise ExtractorError(
            f"LLMWhisperer pdf-to-images job {whisper_hash} did not reach a "
            f"terminal state within {WhispererDefaults.IMAGE_POLL_MAX_ATTEMPTS} "
            "poll attempts",
            status_code=504,
        )

    @staticmethod
    def download_pdf_to_images_zip(config: dict[str, Any], whisper_hash: str) -> BytesIO:
        """Stream the page-image ZIP into an in-memory buffer via chunked reads.

        Uses a distinct, longer download timeout (large multi-page PDFs) and
        avoids a single ``response.content`` load.
        """
        response = LLMWhispererHelper._send_raw_request(
            config=config,
            method="GET",
            endpoint=WhispererEndpoint.PDF_TO_IMAGES_RETRIEVE,
            params={WhisperStatus.WHISPER_HASH: whisper_hash},
            timeout=WhispererDefaults.IMAGE_DOWNLOAD_TIMEOUT,
            stream=True,
        )
        buffer = BytesIO()
        # Consume the stream inside try/finally: map read-time transport errors
        # (ChunkedEncodingError / ConnectionError / read Timeout) to
        # ExtractorError like the rest of the adapter, and always release the
        # connection even if a chunk read fails mid-stream.
        try:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    buffer.write(chunk)
        except requests.RequestException as e:
            logger.error(f"Error streaming pdf-to-images archive: {e}")
            raise ExtractorError(
                "Failed to download the pdf-to-images archive from LLMWhisperer",
                status_code=502,
                actual_err=e,
            ) from e
        finally:
            response.close()
        buffer.seek(0)
        return buffer

    @staticmethod
    def extract_page_images_from_zip(
        zip_buffer: BytesIO,
    ) -> list[tuple[int, bytes]]:
        """Extract page images from the ZIP, ordered ascending by page number.

        Returns ``[(page_number, image_bytes), ...]``. Raises ``ExtractorError``
        on a corrupt/invalid archive.
        """
        pages: list[tuple[int, bytes]] = []
        try:
            with zipfile.ZipFile(zip_buffer) as archive:
                for name in archive.namelist():
                    match = LLMWhispererHelper._PAGE_IMAGE_RE.search(name)
                    if not match:
                        continue
                    page_number = int(match.group(1))
                    pages.append((page_number, archive.read(name)))
        except (zipfile.BadZipFile, RuntimeError, zlib.error) as e:
            # BadZipFile: not a ZIP. RuntimeError: encrypted member.
            # zlib.error: corrupt compressed member surfaced by read().
            raise ExtractorError(
                f"Corrupt or invalid ZIP received from pdf-to-images: {e}",
                status_code=502,
                actual_err=e,
            ) from e
        if not pages:
            # A well-formed archive with no recognizable page images is a
            # failed extraction, not an empty success — fail closed, matching
            # the rest of this flow.
            raise ExtractorError(
                "pdf-to-images returned an archive with no page images",
                status_code=502,
            )
        pages.sort(key=lambda item: item[0])
        return pages

    @staticmethod
    def verify_page_count(
        pages: list[tuple[int, bytes]], processed_page_count: int | None
    ) -> None:
        """Enforce a matching page count against the service's authority.

        The service-reported ``processed_page_count`` is authoritative
        (UNS-746); any mismatch with the extracted count raises.
        """
        if processed_page_count is None:
            # Expected today: the pdf-to-images-status response does not expose a
            # page count (verified vs PR #536). Kept as a forward-compatible hook.
            logger.debug(
                "Image mode: no processed_page_count in status response; "
                "skipping page-count verification"
            )
            return
        actual = len(pages)
        if actual != processed_page_count:
            raise ExtractorError(
                "Page count mismatch in image output mode: service reported "
                f"processed_page_count={processed_page_count} but the extracted "
                f"ZIP contained {actual} page image(s)",
                status_code=502,
            )

    @staticmethod
    def build_page_store_dir(
        output_file_path: str | None, input_file_path: str, run_key: str
    ) -> str:
        """Collision-safe per-document folder for page images (UNS-747).

        ``run_key`` (the unique per-run whisper_hash) isolates every extraction,
        so concurrent documents never share a prefix. Layout:
        ``{base_dir}/{run_key}/pages``.
        """
        reference = output_file_path or input_file_path
        base_dir = str(Path(reference).parent) if reference else "."
        return str(Path(base_dir) / run_key / ImageOutputConfig.PAGES_SUBFOLDER)

    @staticmethod
    def _page_image_filename(page_number: int) -> str:
        padded = str(page_number).zfill(ImageOutputConfig.PAGE_NUMBER_PADDING)
        return (
            f"{ImageOutputConfig.PAGE_IMAGE_PREFIX}{padded}"
            f"{ImageOutputConfig.PAGE_IMAGE_EXTENSION}"
        )

    @staticmethod
    def _write_single_page(fs: FileStorage, path: str, data: bytes) -> None:
        fs.write(path=path, mode="wb", data=data, encoding="utf-8")

    @staticmethod
    def persist_page_images(
        fs: FileStorage,
        page_store_dir: str,
        pages: list[tuple[int, bytes]],
    ) -> list[PageImageReference]:
        """Write every page image to FileStorage with per-page retry.

        All-or-nothing (fail-closed): the full ``PageImageReference`` list is
        only returned once EVERY page is written. If any page exhausts its
        retries, a hard ``ExtractorError`` propagates and no partial set is
        returned (UNS-738 / UNS-739 / UNS-745). Works transparently for LOCAL
        and S3 via the passed ``fs``.
        """
        fs.mkdir(create_parents=True, path=page_store_dir)

        write_with_retry = retry_with_exponential_backoff(
            max_retries=WhispererDefaults.PAGE_STORE_MAX_RETRIES,
            base_delay=WhispererDefaults.RETRY_MIN_WAIT,
            multiplier=2.0,
            jitter=True,
            exceptions=(FileOperationError, OSError),
            logger_instance=logger,
            prefix="LLMW_PAGE_STORE",
        )(LLMWhispererHelper._write_single_page)

        references: list[PageImageReference] = []
        for page_number, data in pages:
            filename = LLMWhispererHelper._page_image_filename(page_number)
            path = str(Path(page_store_dir) / filename)
            try:
                write_with_retry(fs=fs, path=path, data=data)
            except Exception as e:
                raise ExtractorError(
                    "Failed to persist page image after retries: "
                    f"page={page_number}, provider={fs.provider.value}, "
                    f"path={path}",
                    status_code=500,
                    actual_err=e,
                ) from e
            references.append(
                PageImageReference(
                    page_number=page_number,
                    path=path,
                    filename=filename,
                    size_bytes=len(data),
                    provider=fs.provider,
                )
            )
        references.sort(key=lambda ref: ref.page_number)
        logger.info(
            "Image mode: persisted %d page image(s) under %s (provider=%s)",
            len(references),
            page_store_dir,
            fs.provider.value,
        )
        return references

    @staticmethod
    def _download_and_extract(
        config: dict[str, Any], whisper_hash: str
    ) -> list[tuple[int, bytes]]:
        zip_buffer = LLMWhispererHelper.download_pdf_to_images_zip(config, whisper_hash)
        return LLMWhispererHelper.extract_page_images_from_zip(zip_buffer)

    @staticmethod
    def get_page_images(
        config: dict[str, Any],
        input_file_path: str,
        output_file_path: str | None,
        fs: FileStorage | None = None,
        tag: str | list[str] | None = None,
    ) -> list[PageImageReference]:
        """End-to-end image output flow (orchestrator).

        submit -> poll -> download+extract (ONCE) -> verify page count ->
        persist per-page (retried). Returns the ordered ``PageImageReference``
        list, or raises (fail-closed — never partial).

        Retrieval is intentionally NOT retried. Verified against Service
        PR #536: ``pdf-to-images-retrieve`` flips the job to ``RETRIEVED``
        *before* streaming and, with the service default
        ``RESULT_PERSISTENCE=false``, a second retrieve returns
        400 "Result already retrieved". Re-downloading is therefore impossible
        (and re-submitting would double-bill), so a mid-download failure is a
        hard error — the job must be resubmitted by the caller. Per-page
        FileStorage writes (Unstract-side) are still retried.
        """
        if fs is None:
            fs = FileStorage(provider=FileStorageProvider.LOCAL)

        input_data = BytesIO(fs.read(path=input_file_path, mode="rb"))
        whisper_hash = LLMWhispererHelper.submit_pdf_to_images(
            config,
            input_data,
            tag=tag,
            file_name=Path(input_file_path).name,
        )
        status_payload = LLMWhispererHelper.poll_pdf_to_images_status(
            config, whisper_hash
        )
        # NOTE (verified vs PR #536): the status response does NOT expose a page
        # count today — it is billing-internal (pdfToImagesPageCount column).
        # verify_page_count() therefore no-ops unless/until the service adds it.
        processed_page_count = status_payload.get(ImageOutputConfig.PROCESSED_PAGE_COUNT)

        pages = LLMWhispererHelper._download_and_extract(
            config=config, whisper_hash=whisper_hash
        )

        # Verify BEFORE persisting so nothing is written on a count mismatch.
        LLMWhispererHelper.verify_page_count(pages, processed_page_count)

        page_store_dir = LLMWhispererHelper.build_page_store_dir(
            output_file_path=output_file_path,
            input_file_path=input_file_path,
            run_key=whisper_hash,
        )
        references = LLMWhispererHelper.persist_page_images(fs, page_store_dir, pages)
        logger.info(
            "Image mode: completed job=%s pages=%d processed_page_count=%s",
            whisper_hash,
            len(references),
            processed_page_count,
        )
        return references
