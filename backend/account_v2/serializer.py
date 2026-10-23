import re

from rest_framework import serializers
from utils.input_sanitizer import validate_name_field

from account_v2.enums import Product
from account_v2.models import Organization, User


class OrganizationSignupSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, max_length=150)
    display_name = serializers.CharField(required=True, max_length=150)
    organization_id = serializers.CharField(required=True, max_length=30)

    def validate_name(self, value: str) -> str:
        return validate_name_field(value, field_name="Organization name")

    def validate_display_name(self, value: str) -> str:
        return validate_name_field(value, field_name="Display name")

    def validate_organization_id(self, value):  # type: ignore
        if not re.match(r"^[a-z0-9_-]+$", value):
            raise serializers.ValidationError(
                "organization_code should only contain alphanumeric characters,_ and -."
            )
        return value


class OrganizationCallbackSerializer(serializers.Serializer):
    id = serializers.CharField(required=False)


class GetOrganizationsResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    display_name = serializers.CharField()
    name = serializers.CharField()
    # Always sent: allow_null turns a missing attribute into null.
    metadata = serializers.JSONField(allow_null=True)
    # Absent, never null, where this deployment can't answer for the
    # organization: see account_v2/organization_details.py. Absent means
    # unknown, so clients leave it out rather than infer from it.
    role = serializers.CharField(
        required=False,
        help_text="The caller's role. Absent if the caller has no membership "
        "in this organization on this deployment, or if the details could not "
        "be loaded.",
    )
    member_count = serializers.IntegerField(
        required=False,
        help_text="The people the members page lists, without platform API key "
        "accounts. Absent if the organization has no data on this deployment, "
        "if the deployment has regions and the organization's metadata names "
        "another one, or if the details could not be loaded. Organizations "
        "without a region in their metadata count as this deployment's: see "
        "account_v2/ReadMe.md.",
    )
    region = serializers.CharField(
        required=False,
        help_text="The region code, e.g. US or EU, named in the organization's "
        "metadata, else this deployment's region if the organization exists "
        "here. Absent where the deployment has no regions, the region is not "
        "known here, or the details could not be loaded. See account_v2/ReadMe.md "
        "for organizations without a region in their metadata.",
    )

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
    provider = serializers.CharField()
    is_staff = serializers.BooleanField()
    disable_sso_idp_authorization = serializers.BooleanField()
    # The user's last-used product and whether they have ever chosen one.
    last_product = serializers.ChoiceField(choices=Product.choices, allow_null=True)
    has_chosen = serializers.BooleanField()


class ProductPreferenceSerializer(serializers.Serializer):
    product = serializers.ChoiceField(choices=Product.choices, allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    has_chosen = serializers.BooleanField()


class ProductPreferenceUpdateSerializer(serializers.Serializer):
    product = serializers.ChoiceField(choices=Product.choices)
