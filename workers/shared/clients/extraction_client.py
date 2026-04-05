"""Extraction API Client for text extraction callbacks.

Used by the ide_callback worker to persist extraction results
through the backend's internal API endpoints.
"""

import logging
from typing import Any

from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)

_EXTRACTION_COMPLETE_ENDPOINT = "v1/extraction/extraction-complete/"
_EXTRACTION_ERROR_ENDPOINT = "v1/extraction/extraction-error/"


class ExtractionAPIClient(BaseAPIClient):
    """API client for generic text extraction callback endpoints."""

    def mark_extraction_complete(
        self,
        source: str,
        file_id: str,
        token_count: int,
        extracted_text_path: str,
        organization_id: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Notify backend that extraction succeeded."""
        payload: dict[str, Any] = {
            "source": source,
            "file_id": file_id,
            "token_count": token_count,
            "extracted_text_path": extracted_text_path,
            **extra,
        }
        return self.post(
            _EXTRACTION_COMPLETE_ENDPOINT,
            data=payload,
            organization_id=organization_id,
        )

    def mark_extraction_error(
        self,
        source: str,
        file_id: str,
        error: str,
        organization_id: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Notify backend that extraction failed."""
        payload: dict[str, Any] = {
            "source": source,
            "file_id": file_id,
            "error": error,
            **extra,
        }
        return self.post(
            _EXTRACTION_ERROR_ENDPOINT,
            data=payload,
            organization_id=organization_id,
        )
