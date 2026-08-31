import logging
from typing import Any

from adapter_processor_v2.adapter_processor import AdapterProcessor
from adapter_processor_v2.models import AdapterInstance
from backend.serializers import AuditSerializer
from rest_framework.serializers import ValidationError

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
        # Dropped so a duplicate create surfaces the view's DuplicateData.
        validators = []

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject a change to an adapter the requester cannot access.

        An unchanged value passes, so a co-owner can still save a profile
        that points at an adapter shared only with the owner.
        """
        request = self.context.get("request")
        if not request:
            return attrs
        accessible = AdapterInstance.objects.for_user(request.user)
        for field, _ in ADAPTER_LABELS:
            adapter = attrs.get(field)
            if not adapter or adapter == getattr(self.instance, field, None):
                continue
            if not accessible.filter(id=adapter.id).exists():
                raise ValidationError({field: "No access to the selected adapter."})
        return attrs

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
            # Keep the id for adapters the viewer cannot access.
            rep[f"{field}_id"] = str(rep[field])
            rep[field] = adapter.adapter_name
            conf[label] = AdapterProcessor.get_model_label(adapter)
            if field == ProfileManagerKeys.LLM:
                rep["icon"] = AdapterProcessor.get_icon(adapter)
        if conf:
            conf["Profile Name"] = instance.profile_name
        rep["conf"] = conf
        return rep
