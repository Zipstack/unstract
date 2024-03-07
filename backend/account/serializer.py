import re
from account.constants import SubscriptionKeys

# from account.enums import Region
from account.models import Organization, User
from account.subscription_plugin_registry import SubscriptionConfig, load_plugins
from rest_framework import serializers

subscription_loader=load_plugins()
class OrganizationSignupSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, max_length=150)
    display_name = serializers.CharField(required=True, max_length=150)
    organization_id = serializers.CharField(required=True, max_length=30)

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

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        # Modify the representation if needed
        for subscription_plugin in subscription_loader:
            try : 
                cls = subscription_plugin[SubscriptionConfig.METADATA][
                        SubscriptionConfig.METADATA_SERVICE_CLASS
                    ]
                data[SubscriptionKeys.REMAINING_TRIAL_DAYS]=cls.fetch_active_days(
                    organization_id=data[SubscriptionKeys.ORGANIZATION_ID])
            except Exception:
                # To avoid error for missing plugins.
                data = super().to_representation(instance)
        return data



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
        fields = ("id", "email")


class OrganizationSignupResponseSerializer(serializers.Serializer):
    name = serializers.CharField()
    display_name = serializers.CharField()
    organization_id = serializers.CharField()
    created_at = serializers.CharField()
