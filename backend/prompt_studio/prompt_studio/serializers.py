from rest_framework import serializers

from backend.serializers import AuditSerializer

from .models import ToolStudioPrompt


class ToolStudioPromptSerializer(AuditSerializer):
    class Meta:
        model = ToolStudioPrompt
        fields = "__all__"


class ToolStudioIndexSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()
