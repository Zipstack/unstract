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
    single_pass_unresolvable_variables = serializers.SerializerMethodField()

    class Meta:
        model = ToolStudioPrompt
        fields = "__all__"
        # View owns uniqueness (IntegrityError->DuplicateData on create); drop
        # the DRF auto-validator that 400s on re-save / PUT before the view runs.
        validators = []

    def get_single_pass_unresolvable_variables(self, obj) -> list[str]:
        """UN-2900: variables in this prompt that single pass cannot resolve.

        Empty unless the parent tool has single-pass extraction enabled. Lives
        on this serializer rather than the tool serializer so the same value is
        returned by BOTH the tool detail fetch (which nests this serializer per
        prompt) and the prompt save response, without duplicating the logic.

        ``tool_id`` is the FK to CustomTool; callers that serialize many prompts
        should ``select_related("tool_id")`` to avoid a query per prompt.
        """
        from prompt_studio.prompt_studio_core_v2.prompt_variable_service import (
            PromptStudioVariableService,
        )

        tool = getattr(obj, "tool_id", None)
        if not tool or not getattr(tool, "single_pass_extraction_mode", False):
            return []
        if not obj.prompt:
            return []
        return PromptStudioVariableService.find_unresolvable_single_pass_variables(
            prompt=obj.prompt
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
