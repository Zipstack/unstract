import logging

from prompt_studio.prompt_profile_manager.serializers import ProfileManagerSerializer

from backend.serializers import AuditSerializer

from .models import PromptVersionManager

logger = logging.getLogger(__name__)


class PromptVersionManagerSerializer(AuditSerializer):
    profile_manager = ProfileManagerSerializer(
        fields=("profile_id", "llm", "embedding_model", "vector_store", "x2text")
    )

    class Meta:
        model = PromptVersionManager
        fields = ("version", "prompt_key", "prompt", "enforce_type", "profile_manager")
