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

    @staticmethod
    def is_pdf(file_name: str) -> bool:
        """Return True when ``file_name`` is a PDF (case-insensitive suffix)."""
        return Path(file_name).suffix.lower() == ImageOutputConstants.PDF_EXTENSION
