from rest_framework import serializers

from backend.serializers import AuditSerializer

from .models import ToolStudioPrompt


class ToolStudioPromptSerializer(AuditSerializer):
    """Serializer for ToolStudioPrompt model with lookup project validation."""

    lookup_project_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ToolStudioPrompt
        fields = "__all__"

    def get_lookup_project_details(self, obj: ToolStudioPrompt) -> dict | None:
        """Return lookup project name and id if set."""
        if obj.lookup_project:
            return {
                "id": str(obj.lookup_project.id),
                "name": obj.lookup_project.name,
            }
        return None

    def validate_lookup_project(self, value):
        """Validate that the lookup project is linked to the PS project.

        The selected lookup project must be linked at the project level
        via PromptStudioLookupLink before it can be assigned to a prompt.
        """
        if value is None:
            return value

        # Get tool_id from instance (update) or initial data (create)
        tool_id = None
        if self.instance:
            tool_id = self.instance.tool_id_id
        elif "tool_id" in self.initial_data:
            tool_id = self.initial_data["tool_id"]

        if tool_id:
            try:
                from lookup.models import PromptStudioLookupLink

                link_exists = PromptStudioLookupLink.objects.filter(
                    prompt_studio_project_id=tool_id,
                    lookup_project=value,
                ).exists()

                if not link_exists:
                    raise serializers.ValidationError(
                        "Selected lookup project must be linked to this "
                        "Prompt Studio project at the project level first."
                    )
            except ImportError:
                # Lookup app not installed, skip validation
                pass

        return value


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
