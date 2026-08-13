import logging

from adapter_processor_v2.adapter_processor import AdapterProcessor

from backend.serializers import AuditSerializer
from prompt_studio.prompt_profile_manager_v2.constants import ProfileManagerKeys

from .models import ProfileManager

logger = logging.getLogger(__name__)

# Adapter FK -> label shown on the Prompt Studio output tiles.
ADAPTER_LABELS = (
    (ProfileManagerKeys.LLM, "LLM"),
    (ProfileManagerKeys.EMBEDDING_MODEL, "Embedding Model"),
    (ProfileManagerKeys.VECTOR_STORE, "Vector Store"),
    (ProfileManagerKeys.X2TEXT, "Text Extractor"),
)


class ProfileManagerSerializer(AuditSerializer):
    class Meta:
        model = ProfileManager
        fields = "__all__"
        # Uniqueness is enforced by the view; the auto-validator 400s on re-save.
        validators = []

    def to_representation(self, instance):  # type: ignore
        """Resolve the adapter FKs to the name, model and icon the UI renders.

        Not filtered by adapter access - display data only, no credentials.
        """
        rep: dict[str, str] = super().to_representation(instance)
        conf: dict[str, str] = {}
        for field, label in ADAPTER_LABELS:
            adapter = getattr(instance, field, None)
            if not adapter:
                continue
            icon, model = AdapterProcessor.get_display_info(adapter)
            rep[field] = adapter.adapter_name
            conf[label] = model
            if field == ProfileManagerKeys.LLM:
                rep["icon"] = icon
        if conf:
            conf["Profile Name"] = instance.profile_name
        rep["conf"] = conf
        return rep
