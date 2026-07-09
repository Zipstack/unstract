from api_v2.models import APIDeployment
from rest_framework import serializers
from utils.input_sanitizer import validate_safe_text
from utils.user_context import UserContext

from backend.serializers import AuditSerializer
from global_api_deployment_key.models import GlobalApiDeploymentKey


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
    """Used for create/rotate responses where the full key is shown once."""

    class Meta:
        model = GlobalApiDeploymentKey
        fields = ["id", "name", "key", "is_active"]


class GlobalApiDeploymentKeyCreateSerializer(AuditSerializer):
    description = serializers.CharField(required=True, max_length=512)
    api_deployments = serializers.PrimaryKeyRelatedField(
        many=True, queryset=APIDeployment.objects.none(), required=False
    )

    class Meta:
        model = GlobalApiDeploymentKey
        fields = ["name", "description", "allow_all_deployments", "api_deployments"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = UserContext.get_organization()
        # For a many=True relation DRF validates incoming PKs against the
        # *child* relation's queryset. Setting ``.queryset`` on the
        # ManyRelatedField wrapper has no effect, leaving validation against the
        # declared ``APIDeployment.objects.none()`` — which rejects every
        # deployment ("Invalid pk ... object does not exist"). Scope the child
        # relation's queryset so same-org deployments are accepted.
        self.fields[
            "api_deployments"
        ].child_relation.queryset = APIDeployment.objects.filter(
            organization=organization
        )

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

    def validate_description(self, value):
        return validate_safe_text(value)


class GlobalApiDeploymentKeyUpdateSerializer(AuditSerializer):
    api_deployments = serializers.PrimaryKeyRelatedField(
        many=True, queryset=APIDeployment.objects.none(), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = UserContext.get_organization()
        # For a many=True relation DRF validates incoming PKs against the
        # *child* relation's queryset. Setting ``.queryset`` on the
        # ManyRelatedField wrapper has no effect, leaving validation against the
        # declared ``APIDeployment.objects.none()`` — which rejects every
        # deployment ("Invalid pk ... object does not exist"). Scope the child
        # relation's queryset so same-org deployments are accepted.
        self.fields[
            "api_deployments"
        ].child_relation.queryset = APIDeployment.objects.filter(
            organization=organization
        )

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

    def validate_description(self, value):
        return validate_safe_text(value)

    def update(self, instance, validated_data):
        api_deployments = validated_data.pop("api_deployments", None)
        instance = super().update(instance, validated_data)
        if api_deployments is not None:
            instance.api_deployments.set(api_deployments)
        return instance
