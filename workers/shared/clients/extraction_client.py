"""Extraction API Client for text extraction callbacks.

Used by the ide_callback worker to persist extraction results through
the backend's internal API endpoints.

NOTE on scope: the callback endpoints ``v1/extraction/extraction-{complete,error}/``
are currently registered **only** by the cloud ``lookups`` plugin
(see ``pluggable_apps/lookups/internal_urls.py``). The interface is
``source``-dispatched and designed to serve other extraction flows
(prompt-studio docs, connectors) in the future, but in OSS-only builds
the endpoints are absent. Callers from OSS paths should expect a 404
response and treat it as a no-op; the worker's error handling covers
this via a 404-terminal pattern.
"""

import logging
from typing import Any

from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)

_EXTRACTION_COMPLETE_ENDPOINT = "v1/extraction/extraction-complete/"
_EXTRACTION_ERROR_ENDPOINT = "v1/extraction/extraction-error/"


class ExtractionAPIClient(BaseAPIClient):
    """API client for the extraction-callback endpoints registered by
    cloud-side plugins (today: lookups). See module docstring for the
    OSS-absence contract.
    """

    def mark_extraction_complete(
        self,
        source: str,
        file_id: str,
        extracted_text_path: str,
        organization_id: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Notify backend that extraction succeeded."""
        payload: dict[str, Any] = {
            "source": source,
            "file_id": file_id,
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
