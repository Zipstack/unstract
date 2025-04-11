import re

from rest_framework import serializers

from account_v2.models import Organization, User


class OrganizationSignupSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, max_length=150)
    display_name = serializers.CharField(required=True, max_length=150)
    organization_id = serializers.CharField(required=True, max_length=30)

    def validate_organization_id(self, value):  # type: ignore
        if not re.match(r"^[a-z0-9_-]+$", value):
            raise serializers.ValidationError(
                "organization_code should only contain "
                "alphanumeric characters,_ and -."
            )
        return value


class OrganizationCallbackSerializer(serializers.Serializer):
    id = serializers.CharField(required=False)


class GetOrganizationsResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    display_name = serializers.CharField()
    name = serializers.CharField()
    metadata = serializers.JSONField(required=False, allow_null=True)
    # Add more fields as needed

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        # Modify the representation if needed
        return data


class GetOrganizationMembersResponseSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    email = serializers.CharField()
    name = serializers.CharField()
    picture = serializers.CharField()
    # Add more fields as needed

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        # Modify the representation if needed
        return data


class OrganizationSerializer(serializers.Serializer):
    name = serializers.CharField()
    organization_id = serializers.CharField()


class SetOrganizationsResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    email = serializers.CharField()
    name = serializers.CharField()
    display_name = serializers.CharField()
    family_name = serializers.CharField()
    picture = serializers.CharField()
    # Add more fields as needed

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        # Modify the representation if needed
        return data


class ModelTenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = fields = ("name", "created_on")


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


class OrganizationSignupResponseSerializer(serializers.Serializer):
    name = serializers.CharField()
    display_name = serializers.CharField()
    organization_id = serializers.CharField()
    created_at = serializers.CharField()


class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True)

    def validate_username(self, value: str | None) -> str:
        """Check that the username is not empty and has at least 3
        characters.
        """
        if not value or len(value) < 3:
            raise serializers.ValidationError(
                "Username must be at least 3 characters long."
            )
        return value

    def validate_password(self, value: str | None) -> str:
        """Check that the password is not empty and has at least 3
        characters.
        """
        if not value or len(value) < 3:
            raise serializers.ValidationError(
                "Password must be at least 3 characters long."
            )
        return value


class UserSessionResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_id = serializers.CharField()
    email = serializers.CharField()
    organization_id = serializers.CharField()
    role = serializers.CharField()
