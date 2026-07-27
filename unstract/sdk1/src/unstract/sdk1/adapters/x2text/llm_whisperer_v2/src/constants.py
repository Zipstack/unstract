import os
from enum import Enum

from unstract.sdk1.adapters.x2text.constants import ImageOutputConstants


class Modes(Enum):
    NATIVE_TEXT = "native_text"
    LOW_COST = "low_cost"
    HIGH_QUALITY = "high_quality"
    FORM = "form"


class OutputModes(Enum):
    LAYOUT_PRESERVING = "layout_preserving"
    TEXT = "text"
    IMAGE = ImageOutputConstants.IMAGE_MODE


class HTTPMethod(Enum):
    GET = "GET"
    POST = "POST"


class WhispererHeader:
    UNSTRACT_KEY = "unstract-key"


class WhispererEndpoint:
    """Endpoints available at LLMWhisperer service."""

    TEST_CONNECTION = "test-connection"
    WHISPER = "whisper"
    STATUS = "whisper-status"
    RETRIEVE = "whisper-retrieve"
    HIGHLIGHTS = "highlights"
    # Image output mode (pdf-to-images) endpoints. These are NOT exposed by the
    # llmwhisperer-client package, so the adapter calls them via raw requests
    # (decision 2A). See ImageOutputConfig for the assumed service contract.
    PDF_TO_IMAGES = "pdf-to-images"
    PDF_TO_IMAGES_STATUS = "pdf-to-images-status"
    PDF_TO_IMAGES_RETRIEVE = "pdf-to-images-retrieve"


class WhispererEnv:
    """Env variables for LLMWhisperer.

    Can be used to alter behaviour at runtime.

    Attributes:
        WAIT_TIMEOUT: Timeout for the extraction in seconds. Defaults to 300s
        LOG_LEVEL: Logging level for the client library. Defaults to INFO
    """

    WAIT_TIMEOUT = "ADAPTER_LLMW_WAIT_TIMEOUT"
    MAX_RETRIES = "ADAPTER_LLMW_MAX_RETRIES"
    RETRY_MIN_WAIT = "ADAPTER_LLMW_RETRY_MIN_WAIT"
    RETRY_MAX_WAIT = "ADAPTER_LLMW_RETRY_MAX_WAIT"
    # Max retry attempts for per-page FileStorage writes when persisting page
    # images (image output mode). Applies to Unstract-side storage writes only,
    # not to calls made to the LLMWhisperer service.
    PAGE_STORE_MAX_RETRIES = "ADAPTER_LLMW_PAGE_STORE_MAX_RETRIES"
    # Image output mode HTTP tuning. Submit/status calls use a short timeout;
    # the ZIP download uses a distinct, longer timeout (large multi-page PDFs).
    IMAGE_REQUEST_TIMEOUT = "ADAPTER_LLMW_IMAGE_REQUEST_TIMEOUT"
    IMAGE_DOWNLOAD_TIMEOUT = "ADAPTER_LLMW_IMAGE_DOWNLOAD_TIMEOUT"
    IMAGE_POLL_INTERVAL = "ADAPTER_LLMW_IMAGE_POLL_INTERVAL"
    IMAGE_POLL_MAX_ATTEMPTS = "ADAPTER_LLMW_IMAGE_POLL_MAX_ATTEMPTS"
    LOG_LEVEL = "LOG_LEVEL"


class WhispererConfig:
    """Dictionary keys used to configure LLMWhisperer service."""

    URL = "url"
    MODE = "mode"
    OUTPUT_MODE = ImageOutputConstants.OUTPUT_MODE
    UNSTRACT_KEY = "unstract_key"
    MEDIAN_FILTER_SIZE = "median_filter_size"
    GAUSSIAN_BLUR_RADIUS = "gaussian_blur_radius"
    LINE_SPLITTER_TOLERANCE = "line_splitter_tolerance"
    LINE_SPLITTER_STRATEGY = "line_spitter_strategy"
    HORIZONTAL_STRETCH_FACTOR = "horizontal_stretch_factor"
    PAGES_TO_EXTRACT = "pages_to_extract"
    MARK_VERTICAL_LINES = "mark_vertical_lines"
    MARK_HORIZONTAL_LINES = "mark_horizontal_lines"
    PAGE_SEPARATOR = "page_seperator"
    URL_IN_POST = "url_in_post"
    TAG = "tag"
    USE_WEBHOOK = "use_webhook"
    WEBHOOK_METADATA = "webhook_metadata"
    TEXT_ONLY = "text_only"
    WAIT_TIMEOUT = "wait_timeout"
    WAIT_FOR_COMPLETION = "wait_for_completion"
    LOGGING_LEVEL = "logging_level"
    ADD_LINE_NOS = "add_line_nos"
    INCLUDE_LINE_CONFIDENCE = "include_line_confidence"
    EXTRACT_ALL_LINES = "extract_all_lines"
    LINES = "lines"


class WhisperStatus:
    """Values returned / used by /whisper-status endpoint."""

    PROCESSING = "processing"
    PROCESSED = "processed"
    DELIVERED = "delivered"
    UNKNOWN = "unknown"
    # Used for async processing
    WHISPER_HASH = "whisper_hash"
    STATUS = "status"


class WhispererDefaults:
    """Defaults meant for LLMWhisperer."""

    MEDIAN_FILTER_SIZE = 0
    GAUSSIAN_BLUR_RADIUS = 0.0
    FORCE_TEXT_PROCESSING = False
    LINE_SPLITTER_TOLERANCE = 0.75
    LINE_SPLITTER_STRATEGY = "left-priority"
    HORIZONTAL_STRETCH_FACTOR = 1.0
    PAGES_TO_EXTRACT = ""
    PAGE_SEPARATOR = "<<<"
    MARK_VERTICAL_LINES = False
    MARK_HORIZONTAL_LINES = False
    URL_IN_POST = False
    TAG = "default"
    TEXT_ONLY = False
    WAIT_TIMEOUT = int(os.getenv(WhispererEnv.WAIT_TIMEOUT, 900))
    WAIT_FOR_COMPLETION = True
    LOGGING_LEVEL = os.getenv(WhispererEnv.LOG_LEVEL, "INFO")
    MAX_RETRIES = int(os.getenv(WhispererEnv.MAX_RETRIES, 3))
    RETRY_MIN_WAIT = float(os.getenv(WhispererEnv.RETRY_MIN_WAIT, 1.0))
    RETRY_MAX_WAIT = float(os.getenv(WhispererEnv.RETRY_MAX_WAIT, 60.0))
    PAGE_STORE_MAX_RETRIES = int(os.getenv(WhispererEnv.PAGE_STORE_MAX_RETRIES, 3))
    IMAGE_REQUEST_TIMEOUT = int(os.getenv(WhispererEnv.IMAGE_REQUEST_TIMEOUT, 30))
    IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv(WhispererEnv.IMAGE_DOWNLOAD_TIMEOUT, 300))
    IMAGE_POLL_INTERVAL = float(os.getenv(WhispererEnv.IMAGE_POLL_INTERVAL, 3.0))
    IMAGE_POLL_MAX_ATTEMPTS = int(os.getenv(WhispererEnv.IMAGE_POLL_MAX_ATTEMPTS, 100))


class ImageOutputConfig:
    """Config and service contract for LLMWhisperer image output mode.

    The pdf-to-images endpoints are not exposed by the installed
    ``llmwhisperer-client``, so the adapter calls them directly via raw
    ``requests``. The wire shape the adapter depends on is centralised here.

    Flow (base = ``{url}/api/v2``):

    - Submit:   ``POST {base}/pdf-to-images?format=png`` with the PDF bytes
                -> JSON ``{"message": "...", "status": "processing",
                           "whisper_hash": "<run_id>|<data_hash>"}`` (HTTP 202)
    - Status:   ``GET  {base}/pdf-to-images-status?whisper_hash=<id>``
                -> JSON ``{"status": "accepted|processing|processed|...",
                           "message": "..."}``. NOTE: no page count is exposed
                           (page count is billing-internal only).
    - Retrieve: ``GET  {base}/pdf-to-images-retrieve?whisper_hash=<id>``
                -> ``application/zip`` stream of ``page_001.png``, ...
                ONE-TIME by default: the service flips status to ``RETRIEVED``
                before streaming and rejects a second retrieve unless the
                deployment sets ``RESULT_PERSISTENCE=true``. Hence the adapter
                downloads exactly once and never retries the retrieve.
    """

    # --- Response field names ---
    STATUS = "status"
    MESSAGE = "message"

    # Poll control. Success == ready-to-retrieve; only these intermediate states
    # keep the poll loop going. Any other value — a failure state, an unknown
    # status, or an empty/non-JSON body — is treated as terminal and raises, so
    # the loop fails fast instead of polling to the budget on a stuck job.
    STATUS_SUCCESS = frozenset({"processed"})
    STATUS_INTERMEDIATE = frozenset({"accepted", "processing", "queued"})

    # --- Submit query params ---
    IMAGE_FORMAT_PARAM = "format"
    DEFAULT_IMAGE_FORMAT = "png"
    FILE_NAME_PARAM = "file_name"

    # --- Per-page image naming / storage layout ---
    PAGE_IMAGE_PREFIX = "page_"
    PAGE_IMAGE_EXTENSION = ".png"
    PAGE_NUMBER_PADDING = 3
    PAGES_SUBFOLDER = "pages"

    # --- PDF-only validation (shared with the backend index-time guard) ---
    PDF_EXTENSION = ImageOutputConstants.PDF_EXTENSION
    PDF_ONLY_ERROR = ImageOutputConstants.PDF_ONLY_ERROR
    is_pdf = staticmethod(ImageOutputConstants.is_pdf)
