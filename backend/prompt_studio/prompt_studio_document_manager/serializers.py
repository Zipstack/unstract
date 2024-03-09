from backend.serializers import AuditSerializer

from .models import DocumentManager
from .constants import PSDMKeys

class PromptStudioDocumentManagerSerializer(AuditSerializer):
    class Meta:
        model = DocumentManager
        fields = "__all__"
        
    def to_representation(self, instance):
        rep: dict[str, str] = super().to_representation(instance)
        required_fields = [PSDMKeys.DOCUMENT_NAME, PSDMKeys.TOOL, PSDMKeys.PROMPT_DOCUMENT_ID]
        return {key: rep[key] for key in required_fields if key in rep}