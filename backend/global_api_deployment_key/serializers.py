from api_v2.models import APIDeployment
from rest_framework import serializers
from utils.input_sanitizer import validate_safe_text
from utils.user_context import UserContext

from backend.serializers import AuditSerializer
from global_api_deployment_key.models import GlobalApiDeploymentKey

ALLOW_ALL_WITH_LIST_ERROR = {
    "api_deployments": "Leave empty when 'allow all deployments' is enabled."
}
NO_DEPLOYMENTS_SELECTED_ERROR = {
    "api_deployments": (
        "Select at least one deployment or enable 'allow all deployments'."
    )
}


class ApiDeploymentMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for API deployments used in key assignment."""

    class Meta:
        model = APIDeployment
        fields = ["id", "display_name", "api_name", "is_active"]


class GlobalApiDeploymentKeyListSerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()
    api_deployments = ApiDeploymentMinimalSerializer(many=True, read_only=True)

    class Meta:
        model = GlobalApiDeploymentKey
        fields = [
            "id",
            "name",
            "description",
            "key",
            "is_active",
            "allow_all_deployments",
            "api_deployments",
            "created_at",
            "modified_at",
            "created_by_email",
        ]

    def get_key(self, obj):
        key_str = str(obj.key)
        return f"****-{key_str[-4:]}"

    def get_created_by_email(self, obj):
        return obj.created_by.email if obj.created_by else "Deleted user"


class GlobalApiDeploymentKeyDetailSerializer(serializers.ModelSerializer):
    """Exposes the full plaintext key.

    Used by the create/rotate responses and by ``retrieve`` (GET keys/<pk>/),
    so the full key stays retrievable by an org admin for the key's lifetime —
    consistent with the platform_api key flow (not a one-time reveal).
    """

    class Meta:
        model = GlobalApiDeploymentKey
        fields = ["id", "name", "key", "is_active"]


class _GlobalApiDeploymentKeyWriteSerializer(AuditSerializer):
    """Shared write-side surface for the create and update serializers.

    Owns the org-scoped ``api_deployments`` field and the description
    sanitiser; subclasses bring their own ``Meta`` and ``validate``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built here rather than declared as a class attribute: any queryset
        # expression on ``APIDeployment.objects`` runs the org-scoped manager's
        # ``get_queryset``, which resolves ``UserContext.get_organization()`` —
        # so a class-level declaration issues a DB query at *import* time, and
        # blows up wherever the module is imported without a database.
        #
        # The org filter is the guard that stops an admin attaching another
        # org's deployment by UUID.
        self.fields["api_deployments"] = serializers.PrimaryKeyRelatedField(
            many=True,
            required=False,
            queryset=APIDeployment.objects.filter(
                organization=UserContext.get_organization()
            ),
        )

    def validate_description(self, value):
        return validate_safe_text(value)


class GlobalApiDeploymentKeyCreateSerializer(_GlobalApiDeploymentKeyWriteSerializer):
    description = serializers.CharField(required=True, max_length=512)

    class Meta:
        model = GlobalApiDeploymentKey
        fields = ["name", "description", "allow_all_deployments", "api_deployments"]

    def validate_name(self, value):
        value = validate_safe_text(value)
        organization = UserContext.get_organization()
        if GlobalApiDeploymentKey.objects.filter(
            name=value, organization=organization
        ).exists():
            raise serializers.ValidationError(
                "A key with this name already exists in your organization."
            )
        return value

    def validate(self, attrs):
        """Reject incoherent scopes.

        Both fields are always present on create, so an incoherent pair is a
        caller mistake worth surfacing rather than silently normalising:
        ``allow_all`` with a list (the list would be ignored at auth time), or
        neither (a live key that authenticates nothing).
        """
        allow_all = attrs.get("allow_all_deployments", False)
        deployments = attrs.get("api_deployments") or []
        if allow_all and deployments:
            raise serializers.ValidationError(ALLOW_ALL_WITH_LIST_ERROR)
        if not allow_all and not deployments:
            raise serializers.ValidationError(NO_DEPLOYMENTS_SELECTED_ERROR)
        return attrs


class GlobalApiDeploymentKeyUpdateSerializer(_GlobalApiDeploymentKeyWriteSerializer):
    class Meta:
        model = GlobalApiDeploymentKey
        fields = [
            "description",
            "is_active",
            "allow_all_deployments",
            "api_deployments",
        ]
        extra_kwargs = {
            "description": {"required": False},
            "is_active": {"required": False},
            "allow_all_deployments": {"required": False},
        }

    def validate(self, attrs):
        """Validate the effective scope without trapping partial updates.

        Updates are PATCH-only, so a caller may touch one scope field, both, or
        neither. Validating the stored list unconditionally makes two legitimate
        requests fail: flipping a scoped key to allow-all in one field, and
        editing (or deactivating) a key whose only deployment was deleted.
        """
        allow_all = attrs.get(
            "allow_all_deployments",
            self.instance.allow_all_deployments if self.instance else False,
        )
        scope_sent = "api_deployments" in attrs

        if allow_all:
            # ``allow_all`` wins at auth time (see
            # ``GlobalApiDeploymentKey.has_access_to_deployment``), so a list is
            # dead weight. Reject one the caller explicitly sent — they believe
            # they scoped the key — and clear a stale stored one otherwise, so
            # PATCH {"allow_all_deployments": true} works on its own.
            if scope_sent and attrs["api_deployments"]:
                raise serializers.ValidationError(ALLOW_ALL_WITH_LIST_ERROR)
            attrs["api_deployments"] = []
            return attrs

        if scope_sent:
            if not attrs["api_deployments"]:
                raise serializers.ValidationError(NO_DEPLOYMENTS_SELECTED_ERROR)
            return attrs

        if (
            "allow_all_deployments" in attrs
            and not self.instance.api_deployments.exists()
        ):
            # Turning allow-all off without naming deployments would leave a key
            # that authenticates nothing.
            raise serializers.ValidationError(NO_DEPLOYMENTS_SELECTED_ERROR)

        # Scope untouched (e.g. PATCH {"is_active": false}) — deliberately not
        # re-validated, so a key stranded by a deleted deployment stays editable
        # and, more importantly, deactivatable.
        return attrs

    def update(self, instance, validated_data):
        api_deployments = validated_data.pop("api_deployments", None)
        instance = super().update(instance, validated_data)
        if api_deployments is not None:
            instance.api_deployments.set(api_deployments)
        return instance
