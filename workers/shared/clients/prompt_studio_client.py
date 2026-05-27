"""Prompt Studio API Client for IDE Callback Operations

Specialized API client for prompt studio internal endpoints.
Used by the ide_callback worker to persist ORM state through the backend.
"""

import logging
from typing import Any

from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)

# Endpoint paths (relative to internal API base)
_OUTPUT_ENDPOINT = "v1/prompt-studio/output/"
_INDEX_ENDPOINT = "v1/prompt-studio/index/"
_INDEXING_STATUS_ENDPOINT = "v1/prompt-studio/indexing-status/"
_EXTRACTION_STATUS_ENDPOINT = "v1/prompt-studio/extraction-status/"
_PROFILE_ENDPOINT = "v1/prompt-studio/profile/{profile_id}/"
_HUBSPOT_ENDPOINT = "v1/prompt-studio/hubspot-notify/"
_SUMMARY_INDEX_KEY_ENDPOINT = "v1/prompt-studio/summary-index-key/"


class PromptStudioAPIClient(BaseAPIClient):
    """API client for prompt studio internal endpoints.

    All methods call the backend's internal API endpoints which perform
    the actual Django ORM operations.
    """

    def update_prompt_output(
        self,
        run_id: str,
        prompt_ids: list[str],
        outputs: dict[str, Any],
        document_id: str,
        is_single_pass_extract: bool,
        metadata: dict[str, Any],
        profile_manager_id: str | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist prompt execution output via OutputManagerHelper.

        Returns:
            Backend response with serialized output data.
        """
        payload = {
            "run_id": run_id,
            "prompt_ids": prompt_ids,
            "outputs": outputs,
            "document_id": document_id,
            "is_single_pass_extract": is_single_pass_extract,
            "profile_manager_id": profile_manager_id,
            "metadata": metadata,
        }
        return self.post(_OUTPUT_ENDPOINT, data=payload, organization_id=organization_id)

    def update_index_manager(
        self,
        document_id: str,
        profile_manager_id: str,
        doc_id: str,
        is_summary: bool = False,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Update IndexManager after successful indexing."""
        payload = {
            "document_id": document_id,
            "profile_manager_id": profile_manager_id,
            "doc_id": doc_id,
            "is_summary": is_summary,
        }
        return self.post(_INDEX_ENDPOINT, data=payload, organization_id=organization_id)

    def mark_extraction_status(
        self,
        document_id: str,
        profile_manager_id: str,
        x2text_config_hash: str,
        enable_highlight: bool,
        organization_id: str | None = None,
        extracted: bool = True,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Mark IndexManager.extraction_status for a document+profile pair.

        Called from the ide_index_complete callback so that subsequent
        Answer Prompt dispatches can short-circuit re-extraction.
        """
        payload = {
            "document_id": document_id,
            "profile_manager_id": profile_manager_id,
            "x2text_config_hash": x2text_config_hash,
            "enable_highlight": enable_highlight,
            "extracted": extracted,
            "error_message": error_message,
        }
        return self.post(
            _EXTRACTION_STATUS_ENDPOINT, data=payload, organization_id=organization_id
        )

    def mark_document_indexed(
        self,
        org_id: str,
        user_id: str,
        doc_id_key: str,
        doc_id: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Mark a document as indexed in the cache."""
        payload = {
            "action": "mark_indexed",
            "org_id": org_id,
            "user_id": user_id,
            "doc_id_key": doc_id_key,
            "doc_id": doc_id,
        }
        return self.post(
            _INDEXING_STATUS_ENDPOINT, data=payload, organization_id=organization_id
        )

    def remove_document_indexing(
        self,
        org_id: str,
        user_id: str,
        doc_id_key: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Remove the document indexing flag from cache."""
        payload = {
            "action": "remove",
            "org_id": org_id,
            "user_id": user_id,
            "doc_id_key": doc_id_key,
        }
        return self.post(
            _INDEXING_STATUS_ENDPOINT, data=payload, organization_id=organization_id
        )

    def get_profile(
        self,
        profile_id: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Get profile manager details (adapter IDs, chunk settings)."""
        endpoint = _PROFILE_ENDPOINT.format(profile_id=profile_id)
        return self.get(endpoint, organization_id=organization_id)

    def notify_hubspot(
        self,
        user_id: str,
        event_name: str,
        is_first_for_org: bool = False,
        action_label: str = "",
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Fire a HubSpot event notification."""
        payload = {
            "user_id": user_id,
            "event_name": event_name,
            "is_first_for_org": is_first_for_org,
            "action_label": action_label,
        }
        return self.post(_HUBSPOT_ENDPOINT, data=payload, organization_id=organization_id)

    def get_summary_index_key(
        self,
        summary_profile_id: str,
        summarize_file_path: str,
        org_id: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Compute summary doc_id hash server-side.

        The computation requires PromptIdeBaseTool + IndexingUtils which depend
        on Django ORM and are only available on the backend image.
        """
        payload = {
            "summary_profile_id": summary_profile_id,
            "summarize_file_path": summarize_file_path,
            "org_id": org_id,
        }
        return self.post(
            _SUMMARY_INDEX_KEY_ENDPOINT, data=payload, organization_id=organization_id
        )
