from backend.serializers import AuditSerializer

from .models import PromptStudioOutputManager


class PromptStudioOutputSerializer(AuditSerializer):
    class Meta:
        model = PromptStudioOutputManager
        fields = "__all__"

