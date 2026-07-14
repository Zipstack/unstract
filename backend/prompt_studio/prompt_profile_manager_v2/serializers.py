import logging

from adapter_processor_v2.adapter_processor import AdapterProcessor
from rest_framework import serializers

from backend.serializers import AuditSerializer
from prompt_studio.prompt_profile_manager_v2.constants import ProfileManagerKeys

from .models import ProfileManager

logger = logging.getLogger(__name__)

# Extraction adapter fields that are only required when at least one prompt
# using this profile needs text extraction (extraction_inputs != "image").
_TEXT_EXTRACTION_FIELDS = (
    ProfileManagerKeys.VECTOR_STORE,
    ProfileManagerKeys.EMBEDDING_MODEL,
    ProfileManagerKeys.X2TEXT,
)


class ProfileManagerSerializer(AuditSerializer):
    class Meta:
        model = ProfileManager
        fields = "__all__"
        # View owns uniqueness (IntegrityError->DuplicateData on create); drop
        # the DRF auto-validator that 400s on re-save / PUT before the view runs.
        validators = []

    def validate(self, attrs):
        """Enforce x2text/embedding/vector_store when text extraction needed.

        These fields are nullable at the DB level to support image-only
        profiles, but must be populated when any prompt using this profile
        requires text extraction.
        """
        attrs = super().validate(attrs)

        instance = self.instance
        if instance is not None:
            # Update: check prompts currently linked to this profile
            needs_text = instance.tool_studio_prompts.exclude(
                extraction_inputs="image"
            ).exists()
        else:
            # Create: no prompts linked yet — require extraction adapters
            # by default so existing flows are unaffected
            needs_text = True

        if needs_text:
            missing = [
                field
                for field in _TEXT_EXTRACTION_FIELDS
                if not attrs.get(field)
                and (instance is None or not getattr(instance, f"{field}_id", None))
            ]
            if missing:
                raise serializers.ValidationError(
                    {
                        field: "This field is required when any linked prompt "
                        "uses text extraction."
                        for field in missing
                    }
                )
        return attrs

    def to_representation(self, instance):  # type: ignore
        rep: dict[str, str] = super().to_representation(instance)
        llm = rep[ProfileManagerKeys.LLM]
        embedding = rep.get(ProfileManagerKeys.EMBEDDING_MODEL)
        vector_db = rep.get(ProfileManagerKeys.VECTOR_STORE)
        x2text = rep.get(ProfileManagerKeys.X2TEXT)
        if llm:
            rep[ProfileManagerKeys.LLM] = AdapterProcessor.get_adapter_instance_by_id(llm)
        if embedding:
            rep[ProfileManagerKeys.EMBEDDING_MODEL] = (
                AdapterProcessor.get_adapter_instance_by_id(embedding)
            )
        if vector_db:
            rep[ProfileManagerKeys.VECTOR_STORE] = (
                AdapterProcessor.get_adapter_instance_by_id(vector_db)
            )
        if x2text:
            rep[ProfileManagerKeys.X2TEXT] = AdapterProcessor.get_adapter_instance_by_id(
                x2text
            )
        return rep
