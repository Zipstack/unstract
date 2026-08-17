import logging
from typing import Any

from adapter_processor_v2.adapter_processor import AdapterProcessor

from backend.serializers import AuditSerializer
from prompt_studio.prompt_profile_manager_v2.constants import ProfileManagerKeys

from .models import ProfileManager

logger = logging.getLogger(__name__)

# Adapter FK -> "conf" response key read by the UI.
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
        # Drop DRF's auto unique-together validator so a duplicate create
        # surfaces the view's DuplicateData instead of DRF's generic message.
        validators = []

    def to_representation(self, instance):  # type: ignore
        """Resolve the adapter FKs to the name, model and icon the UI renders.

        Not filtered by adapter access - display data only, no credentials.
        """
        rep: dict[str, Any] = super().to_representation(instance)
        conf: dict[str, str] = {}
        for field, label in ADAPTER_LABELS:
            adapter = getattr(instance, field)
            if not adapter:
                continue
            rep[field] = adapter.adapter_name
            conf[label] = AdapterProcessor.get_model_label(adapter)
            if field == ProfileManagerKeys.LLM:
                rep["icon"] = AdapterProcessor.get_icon(adapter)
        if conf:
            conf["Profile Name"] = instance.profile_name
        rep["conf"] = conf
        return rep
