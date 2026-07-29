from pathlib import Path


class X2TextConstants:
    PLATFORM_SERVICE_API_KEY = "PLATFORM_SERVICE_API_KEY"
    X2TEXT_HOST = "X2TEXT_HOST"
    X2TEXT_PORT = "X2TEXT_PORT"
    ENABLE_HIGHLIGHT = "enable_highlight"
    TAGS = "tags"
    EXTRACTED_TEXT = "extracted_text"
    WHISPER_HASH = "whisper-hash"
    WHISPER_HASH_V2 = "whisper_hash"


class ImageOutputConstants:
    """Image-output-mode contract shared across the x2text layer.

    Kept on the generic x2text surface (not inside an adapter's private
    ``src/`` package) so consumers outside the adapter — e.g. the backend's
    index-time PDF-only guard — depend on it without reaching into adapter
    internals.
    """

    # Adapter config key selecting the output format, and the value that
    # selects per-page image output.
    OUTPUT_MODE = "output_mode"
    IMAGE_MODE = "image"

    # Image output accepts PDF input only. A single message + a single
    # extension test keep the runtime guard (adapter ``process()``) and the
    # index-time guard (backend) from drifting apart.
    PDF_EXTENSION = ".pdf"
    PDF_ONLY_ERROR = (
        "Image output mode supports PDF input only. "
        "Please provide a PDF file or select a text output mode."
    )

    # --- Page image storage layout (writer/reader contract) ---
    # The adapter (writer) persists one PNG per page under a ``pages``
    # subfolder as ``page_NNN.png`` (zero-padded to PAGE_NUMBER_PADDING
    # digits; four or more digits appear naturally past page 999). Readers
    # discover pages with PAGE_GLOB_PATTERN and MUST order them by the
    # integer captured by PAGE_NUMBER_REGEX — never lexicographically,
    # which silently misorders once page numbers outgrow the padding.
    PAGES_SUBFOLDER = "pages"
    PAGE_IMAGE_PREFIX = "page_"
    PAGE_IMAGE_EXTENSION = ".png"
    PAGE_NUMBER_PADDING = 3
    PAGE_GLOB_PATTERN = "page_*.png"
    # First capture group is the numeric page index (as a string, possibly
    # zero-padded) — cast to int before sorting.
    PAGE_NUMBER_REGEX = r"page_(\d+)\.png"

    # Leading bytes of every PDF file — the content-based check for inputs
    # whose storage name carries no extension (workflow executions store the
    # source file under an extension-less name like ``SOURCE``).
    PDF_MAGIC_BYTES = b"%PDF-"

    @staticmethod
    def is_pdf(file_name: str) -> bool:
        """Return True when ``file_name`` is a PDF (case-insensitive suffix)."""
        return Path(file_name).suffix.lower() == ImageOutputConstants.PDF_EXTENSION

    @staticmethod
    def is_pdf_bytes(header: bytes) -> bool:
        """Return True when ``header`` starts with the PDF magic bytes."""
        return bytes(header).startswith(ImageOutputConstants.PDF_MAGIC_BYTES)


def build_page_store_dir(output_file_path: str | None, input_file_path: str) -> str:
    """Per-document folder for page images: ``{extract_dir}/{stem}/pages``.

    The single canonical derivation shared by the adapter (writer) and any
    page-image reader, so both sides agree on the location without metadata
    persistence or a manifest sidecar. Keyed on the document ``stem`` (the
    same discriminator the extract ``.txt`` files alongside use), not the
    per-run whisper_hash. This is collision-safe against concurrent documents
    in the same project, is reconstructible from ``output_file_path`` alone,
    and — being stable across runs — makes a re-extraction overwrite its own
    pages instead of orphaning a fresh tree in FileStorage on every run.

    Pure and deterministic: no I/O, no lookups.
    """
    reference = output_file_path or input_file_path
    base_dir = str(Path(reference).parent) if reference else "."
    stem = Path(reference).stem if reference else "document"
    return str(Path(base_dir) / stem / ImageOutputConstants.PAGES_SUBFOLDER)
