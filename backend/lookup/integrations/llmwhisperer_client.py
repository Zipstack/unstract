"""LLMWhisperer integration for document text extraction.

This module provides integration with LLMWhisperer service
for extracting text from various document formats.
"""

import logging
import time
from enum import Enum
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ExtractionStatus(Enum):
    """Status of document extraction."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    NOT_REQUIRED = "not_required"


class LLMWhispererClient:
    """Client for integrating with LLMWhisperer document extraction service.

    LLMWhisperer extracts text from PDFs, images, and other document formats
    for use as reference data in Look-Ups.
    """

    def __init__(self):
        """Initialize LLMWhisperer client with configuration."""
        self.base_url = getattr(
            settings, "LLMWHISPERER_BASE_URL", "https://api.llmwhisperer.com"
        )
        self.api_key = getattr(settings, "LLMWHISPERER_API_KEY", "")

        if not self.api_key:
            logger.warning("LLMWhisperer API key not configured")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )

    def extract_text(
        self,
        file_content: bytes,
        file_name: str,
        extraction_config: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Extract text from a document using LLMWhisperer.

        Args:
            file_content: File content as bytes
            file_name: Original file name
            extraction_config: Optional extraction configuration

        Returns:
            Tuple of (extraction_id, status)
        """
        if not self.api_key:
            logger.error("LLMWhisperer API key not configured")
            return "", ExtractionStatus.FAILED.value

        try:
            # Prepare extraction request
            config = extraction_config or self._get_default_config()

            # Create extraction job
            url = f"{self.base_url}/v1/extract"

            # Prepare multipart form data
            files = {"file": (file_name, file_content)}

            # Add configuration as form data
            data = {
                "processing_mode": config.get("processing_mode", "ocr"),
                "output_format": config.get("output_format", "text"),
                "page_separator": config.get("page_separator", "\n---\n"),
                "force_text_processing": str(
                    config.get("force_text_processing", True)
                ).lower(),
                "line_splitter": config.get("line_splitter", "line"),
                "horizontal_stretch": str(config.get("horizontal_stretch", 1.0)),
                "vertical_stretch": str(config.get("vertical_stretch", 1.0)),
            }

            # Remove JSON content type for multipart
            headers = {"Authorization": f"Bearer {self.api_key}"}

            response = requests.post(
                url, files=files, data=data, headers=headers, timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                extraction_id = result.get("extraction_id", "")
                logger.info(f"Started extraction job: {extraction_id}")
                return extraction_id, ExtractionStatus.PROCESSING.value
            else:
                logger.error(
                    f"Extraction failed with status {response.status_code}: {response.text}"
                )
                return "", ExtractionStatus.FAILED.value

        except requests.exceptions.RequestException as e:
            logger.error(f"LLMWhisperer extraction request failed: {e}")
            return "", ExtractionStatus.FAILED.value
        except Exception as e:
            logger.error(f"Unexpected error during extraction: {e}")
            return "", ExtractionStatus.FAILED.value

    def check_extraction_status(self, extraction_id: str) -> tuple[str, str | None]:
        """Check the status of an extraction job.

        Args:
            extraction_id: Extraction job ID

        Returns:
            Tuple of (status, extracted_text)
        """
        if not extraction_id:
            return ExtractionStatus.FAILED.value, None

        try:
            url = f"{self.base_url}/v1/status/{extraction_id}"

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                result = response.json()
                status = result.get("status", "unknown")

                if status == "completed":
                    # Get extracted text
                    text = self._get_extracted_text(extraction_id)
                    return ExtractionStatus.COMPLETE.value, text
                elif status == "processing":
                    return ExtractionStatus.PROCESSING.value, None
                elif status == "failed":
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"Extraction {extraction_id} failed: {error_msg}")
                    return ExtractionStatus.FAILED.value, None
                else:
                    logger.warning(f"Unknown extraction status: {status}")
                    return ExtractionStatus.PENDING.value, None
            else:
                logger.error(f"Status check failed with code {response.status_code}")
                return ExtractionStatus.FAILED.value, None

        except Exception as e:
            logger.error(f"Error checking extraction status: {e}")
            return ExtractionStatus.FAILED.value, None

    def _get_extracted_text(self, extraction_id: str) -> str | None:
        """Retrieve extracted text for a completed job.

        Args:
            extraction_id: Extraction job ID

        Returns:
            Extracted text or None
        """
        try:
            url = f"{self.base_url}/v1/result/{extraction_id}"

            response = self.session.get(url, timeout=30)

            if response.status_code == 200:
                # Response is the extracted text
                return response.text
            else:
                logger.error(f"Failed to get extraction result: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error retrieving extracted text: {e}")
            return None

    def wait_for_extraction(
        self, extraction_id: str, max_wait_seconds: int = 300, poll_interval: int = 5
    ) -> tuple[str, str | None]:
        """Wait for extraction to complete with polling.

        Args:
            extraction_id: Extraction job ID
            max_wait_seconds: Maximum time to wait
            poll_interval: Seconds between status checks

        Returns:
            Tuple of (final_status, extracted_text)
        """
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            status, text = self.check_extraction_status(extraction_id)

            if status == ExtractionStatus.COMPLETE.value:
                logger.info(f"Extraction {extraction_id} completed successfully")
                return status, text
            elif status == ExtractionStatus.FAILED.value:
                logger.error(f"Extraction {extraction_id} failed")
                return status, None
            elif status == ExtractionStatus.PROCESSING.value:
                logger.debug(f"Extraction {extraction_id} still processing...")
                time.sleep(poll_interval)
            else:
                logger.warning(f"Unexpected status for {extraction_id}: {status}")
                time.sleep(poll_interval)

        logger.error(
            f"Extraction {extraction_id} timed out after {max_wait_seconds} seconds"
        )
        return ExtractionStatus.FAILED.value, None

    def extract_and_wait(
        self,
        file_content: bytes,
        file_name: str,
        extraction_config: dict[str, Any] | None = None,
        max_wait_seconds: int = 300,
    ) -> tuple[bool, str | None]:
        """Extract text and wait for completion.

        Args:
            file_content: File content
            file_name: File name
            extraction_config: Extraction configuration
            max_wait_seconds: Maximum wait time

        Returns:
            Tuple of (success, extracted_text)
        """
        # Start extraction
        extraction_id, status = self.extract_text(
            file_content, file_name, extraction_config
        )

        if status == ExtractionStatus.FAILED.value:
            return False, None

        # Wait for completion
        final_status, text = self.wait_for_extraction(extraction_id, max_wait_seconds)

        return final_status == ExtractionStatus.COMPLETE.value, text

    def _get_default_config(self) -> dict[str, Any]:
        """Get default extraction configuration.

        Returns:
            Default configuration dictionary
        """
        return {
            "processing_mode": "ocr",  # 'ocr' or 'text'
            "output_format": "text",  # 'text' or 'markdown'
            "page_separator": "\n---\n",
            "force_text_processing": True,
            "line_splitter": "line",  # 'line' or 'paragraph'
            "horizontal_stretch": 1.0,
            "vertical_stretch": 1.0,
            "pages": "",  # Empty for all pages
            "timeout": 300,
            "store_metadata": False,
        }

    def is_extraction_needed(self, file_name: str) -> bool:
        """Check if extraction is needed for the file type.

        Args:
            file_name: File name with extension

        Returns:
            True if extraction is needed
        """
        # File types that need extraction
        extractable_extensions = {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".bmp",
            ".docx",
            ".doc",
            ".pptx",
            ".ppt",
            ".xlsx",
            ".xls",
        }

        # Check file extension
        import os

        _, ext = os.path.splitext(file_name.lower())
        return ext in extractable_extensions

    def get_extraction_config_for_file(self, file_name: str) -> dict[str, Any]:
        """Get optimal extraction configuration based on file type.

        Args:
            file_name: File name with extension

        Returns:
            Extraction configuration
        """
        import os

        _, ext = os.path.splitext(file_name.lower())

        config = self._get_default_config()

        # Optimize based on file type
        if ext in [".pdf"]:
            config["processing_mode"] = "ocr"
            config["force_text_processing"] = True
        elif ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
            config["processing_mode"] = "ocr"
            config["force_text_processing"] = False
        elif ext in [".docx", ".doc"]:
            config["processing_mode"] = "text"
            config["output_format"] = "markdown"
        elif ext in [".xlsx", ".xls"]:
            config["processing_mode"] = "text"
            config["line_splitter"] = "paragraph"

        return config
