from collections import OrderedDict
from typing import Any, cast

from account_v2.constants import Common
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer

from tenant_account_v2.models import OrganizationMember


class OrganizationCallbackSerializer(serializers.Serializer):
    id = serializers.CharField(required=False)


class OrganizationLoginResponseSerializer(serializers.Serializer):
    name = serializers.CharField()
    display_name = serializers.CharField()
    organization_id = serializers.CharField()
    created_at = serializers.CharField()


class UserInviteResponseSerializer(serializers.Serializer):
    email = serializers.CharField(required=True)
    status = serializers.CharField(required=True)
    message = serializers.CharField(required=False)


class OrganizationMemberSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source="user.email", read_only=True)
    id = serializers.CharField(source="user.id", read_only=True)

    class Meta:
        model = OrganizationMember
        fields = ("id", "email", "role")


class LimitedUserEmailListSerializer(serializers.ListSerializer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.max_elements: int = kwargs.pop("max_elements", Common.MAX_EMAIL_IN_REQUEST)
        super().__init__(*args, **kwargs)

    def validate(self, data: list[str]) -> Any:
        if len(data) > self.max_elements:
            raise ValidationError(
                f"Exceeded maximum number of elements ({self.max_elements})"
            )
        return data


class LimitedUserListSerializer(serializers.ListSerializer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.max_elements: int = kwargs.pop("max_elements", Common.MAX_EMAIL_IN_REQUEST)
        super().__init__(*args, **kwargs)

    def validate(self, data: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
        if len(data) > self.max_elements:
            raise ValidationError(
                f"Exceeded maximum number of elements ({self.max_elements})"
            )

        for item in data:
            if not isinstance(item, dict):
                raise ValidationError("Each item in the list must be a dictionary.")
            if "email" not in item:
                raise ValidationError("Each item in the list must have 'email' key.")
            if "role" not in item:
                item["role"] = None

        return data


class InviteUserSerializer(serializers.Serializer):
    users = LimitedUserListSerializer(
        required=True,
        child=serializers.DictField(
            child=serializers.CharField(max_length=255, required=True),
            required=False,  # Make 'role' field optional
        ),
        max_elements=Common.MAX_EMAIL_IN_REQUEST,
    )

    def get_users(self, validated_data: dict[str, Any]) -> list[dict[str, str | None]]:
        return validated_data.get("users", [])


class RemoveUserFromOrganizationSerializer(serializers.Serializer):
    emails = LimitedUserEmailListSerializer(
        required=True,
        child=serializers.EmailField(required=True),
        max_elements=Common.MAX_EMAIL_IN_REQUEST,
    )

    def get_user_emails(self, validated_data: dict[str, list[str] | None]) -> list[str]:
        return cast("list[str]", validated_data.get(Common.USER_EMAILS, []))


class ChangeUserRoleRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    role = serializers.CharField(required=True)

    def get_user_email(self, validated_data: dict[str, str | None]) -> str | None:
        return validated_data.get(Common.USER_EMAIL)

    def get_user_role(self, validated_data: dict[str, str | None]) -> str | None:
        return validated_data.get(Common.USER_ROLE)


class DeleteInvitationRequestSerializer(serializers.Serializer):
    id = serializers.EmailField(required=True)

    def get_id(self, validated_data: dict[str, str | None]) -> str | None:
        return validated_data.get(Common.ID)


class UserInfoSerializer(serializers.Serializer):
    id = serializers.CharField()
    email = serializers.CharField()
    name = serializers.CharField()
    display_name = serializers.CharField()
    family_name = serializers.CharField()
    picture = serializers.CharField()


class GetRolesResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()

    def to_representation(self, instance: Any) -> OrderedDict[str, Any]:
        data: OrderedDict[str, Any] = super().to_representation(instance)
        return data


class ListInvitationsResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    email = serializers.CharField()
    created_at = serializers.CharField()
    expires_at = serializers.CharField()

    def to_representation(self, instance: Any) -> OrderedDict[str, Any]:
        data: OrderedDict[str, Any] = super().to_representation(instance)
        return data


class UpdateFlagSerializer(ModelSerializer):
    class Meta:
        model = OrganizationMember
        fields = ("is_login_onboarding_msg", "is_prompt_studio_onboarding_msg")
