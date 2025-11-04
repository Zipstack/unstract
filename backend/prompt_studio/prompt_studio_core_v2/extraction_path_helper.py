import logging
import os

logger = logging.getLogger(__name__)


class ExtractionPathHelper:
    """Helper class for managing extraction file paths with highlight support.

    Provides utilities to generate file paths for extracted text, with support
    for separate storage of highlighted vs non-highlighted versions.

    Storage Pattern:
        - Non-highlighted: extract/filename_plain.txt
        - Highlighted: extract/filename_highlighted.txt

    Note: Old files without suffix (extract/filename.txt) are NOT used and will
    trigger re-extraction. This ensures no ambiguity between old and new formats.
    """

    PLAIN_SUFFIX = "_plain"
    HIGHLIGHT_SUFFIX = "_highlighted"

    @staticmethod
    def get_extraction_path(
        base_dir: str, filename: str, enable_highlight: bool = False
    ) -> str:
        """Get extraction file path with explicit suffix for both modes.

        Args:
            base_dir: Base directory containing the extract folder
            filename: Original filename (with or without extension)
            enable_highlight: Whether highlighting is enabled

        Returns:
            Full path to the extraction file

        Example:
            >>> ExtractionPathHelper.get_extraction_path("/data", "doc.pdf", False)
            "/data/extract/doc_plain.txt"
            >>> ExtractionPathHelper.get_extraction_path("/data", "doc.pdf", True)
            "/data/extract/doc_highlighted.txt"
        """
        base_name = os.path.splitext(filename)[0]
        # Always use explicit suffix for both highlighted and non-highlighted modes
        suffix = (
            ExtractionPathHelper.HIGHLIGHT_SUFFIX
            if enable_highlight
            else ExtractionPathHelper.PLAIN_SUFFIX
        )
        extract_filename = f"{base_name}{suffix}.txt"
        return os.path.join(base_dir, "extract", extract_filename)
