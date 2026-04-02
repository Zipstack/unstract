import logging

from rest_framework import serializers

from backend.serializers import AuditSerializer
from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import PromptStudioHelper

from .models import ToolStudioPrompt

logger = logging.getLogger(__name__)


class ToolStudioPromptSerializer(AuditSerializer):
    class Meta:
        model = ToolStudioPrompt
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Extend enforce_type choices with plugin-provided options
        if "enforce_type" in self.fields:
            base_choices = list(ToolStudioPrompt.EnforceType.choices)
            try:
                select_fields = PromptStudioHelper.get_select_fields()
                plugin_output_types = select_fields.get("output_type", {})
                existing_values = {c[0] for c in base_choices}
                for value in plugin_output_types.values():
                    if value not in existing_values:
                        base_choices.append((value, value))
            except Exception:
                logger.exception(
                    "Failed to load plugin choices for enforce_type"
                )
            self.fields["enforce_type"] = serializers.ChoiceField(
                choices=base_choices, required=False, allow_blank=True
            )


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
