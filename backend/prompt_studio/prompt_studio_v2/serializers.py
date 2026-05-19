from rest_framework import serializers

from backend.serializers import AuditSerializer

from .models import ToolStudioPrompt


class ToolStudioPromptListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing prompts by tool.

    Returns only the fields needed for linking/display without
    output data or coverage calculation.
    """

    class Meta:
        model = ToolStudioPrompt
        fields = [
            "prompt_id",
            "prompt_key",
            "enforce_type",
            "sequence_number",
        ]


class ToolStudioPromptSerializer(AuditSerializer):
    class Meta:
        model = ToolStudioPrompt
        fields = "__all__"


class ToolStudioIndexSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()


class ReorderPromptsSerializer(serializers.Serializer):
    start_sequence_number = serializers.IntegerField(required=True)
    end_sequence_number = serializers.IntegerField(required=True)
    prompt_id = serializers.CharField(required=True)

    def validate(self, data):
        start_sequence_number = data.get("start_sequence_number")
        end_sequence_number = data.get("end_sequence_number")

        if start_sequence_number == end_sequence_number:
            raise serializers.ValidationError(
                "Start and end sequence numbers cannot be the same."
            )

        return data
