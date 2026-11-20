from typing import Any

from backend.serializers import AuditSerializer

from .constants import IndexStatus, PSDMKeys
from .models import DocumentManager


def index_status(document: DocumentManager) -> list[dict[str, Any]]:
    """Each of the tool's LLM profiles with this document's index state.

    failed: the last indexing failed (cleared when the document is next
    indexed; a summary index leaves it).
    indexed: a raw index exists. pending: neither.
    """
    managers = {im.profile_manager_id: im for im in document.index_managers.all()}
    statuses = []
    for profile in document.tool.profile_managers.all():
        manager = managers.get(profile.profile_id)
        if manager and manager.index_error:
            state = IndexStatus.FAILED
        elif manager and manager.raw_index_id:
            state = IndexStatus.INDEXED
        else:
            state = IndexStatus.PENDING
        statuses.append(
            {
                "profile_manager": str(profile.profile_id),
                "is_default": profile.is_default,
                "status": state,
                "failure_reason": manager.index_error
                if state == IndexStatus.FAILED
                else None,
            }
        )
    return statuses


class PromptStudioDocumentManagerSerializer(AuditSerializer):
    class Meta:
        model = DocumentManager
        fields = "__all__"

    def to_representation(self, instance: DocumentManager) -> dict[str, Any]:
        rep: dict[str, str] = super().to_representation(instance)
        required_fields = [
            PSDMKeys.DOCUMENT_NAME,
            PSDMKeys.TOOL,
            PSDMKeys.DOCUMENT_ID,
        ]
        return {key: rep[key] for key in required_fields if key in rep}


class PromptStudioDocumentStatusSerializer(PromptStudioDocumentManagerSerializer):
    """The prompt-document list: adds size, pages and per-profile index state.

    Kept off the base serializer, which public shares also render: the
    failure reason is provider error text meant for the tool's own users.
    """

    def to_representation(self, instance: DocumentManager) -> dict[str, Any]:
        data = super().to_representation(instance)
        data[PSDMKeys.SIZE_BYTES] = instance.size_bytes
        data[PSDMKeys.PAGE_COUNT] = instance.page_count
        data[PSDMKeys.INDEX_STATUS] = index_status(instance)
        return data
