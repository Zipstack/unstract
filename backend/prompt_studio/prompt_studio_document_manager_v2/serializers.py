from typing import Any

from backend.serializers import AuditSerializer

from .constants import PSDMKeys
from .models import DocumentManager


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
