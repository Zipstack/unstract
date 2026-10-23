from collections import OrderedDict
from typing import Any, cast

from account_v2.constants import Common
from account_v2.models import NAME_SIZE
from account_v2.user_profile import LANGUAGES, MAX_PHOTO_BYTES, PHOTO_TYPES
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer
from utils.FileValidator import FileValidator

from tenant_account_v2.capabilities import (
    CAPABILITY_KEY_VALUES,
    CAPABILITY_SETTING_VALUES,
    SPECS,
    SPECS_BY_KEY,
    CapabilitySetting,
)
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
    is_admin = serializers.SerializerMethodField()
    is_service_account = serializers.BooleanField(
        source="user.is_service_account", read_only=True
    )

    class Meta:
        model = OrganizationMember
        fields = ("id", "email", "role", "is_admin", "is_service_account")

    def get_is_admin(self, obj: OrganizationMember) -> bool:
        # Admin determination is auth-plugin specific (OSS "admin" vs Auth0
        # "unstract_admin"); defer to the same check used for access control.
        auth_controller = self.context.get("auth_controller")
        if auth_controller is None:
            from account_v2.authentication_controller import AuthenticationController

            auth_controller = AuthenticationController()
        return auth_controller.is_admin_by_role(obj.role)


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
        return cast(list[str], validated_data.get(Common.USER_EMAILS, []))


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


class UserProfileSerializer(UserInfoSerializer):
    """The `user` object GET users/profile/ returns; documents the contract."""

    # The identity provider's user info may leave these out.
    id = serializers.CharField(allow_null=True)
    name = serializers.CharField(
        allow_null=True, help_text="The edited name when set, else the provider's"
    )
    display_name = serializers.CharField(
        allow_null=True, help_text="The edited name when set, else the provider's"
    )
    family_name = serializers.CharField(allow_null=True)
    picture = serializers.CharField(
        allow_null=True,
        help_text="`photo_url` when a photo is set, else the provider's picture",
    )
    is_admin = serializers.BooleanField()
    login_onboarding_message_displayed = serializers.BooleanField()
    prompt_onboarding_message_displayed = serializers.BooleanField()
    role = serializers.CharField()
    organization_name = serializers.CharField(required=False)
    organization_id = serializers.CharField(required=False)
    photo_url = serializers.CharField(
        allow_null=True,
        help_text="Org-scoped URL of GET users/profile/photo/, null when no photo",
    )
    language = serializers.CharField(help_text="BCP 47 tag; only `en-US` for now")


class ProfileUpdateSerializer(serializers.Serializer):
    # validated_data is keyed by the model field the value is saved to.
    display_name = serializers.CharField(
        max_length=NAME_SIZE, source="profile_display_name"
    )
    language = serializers.ChoiceField(choices=LANGUAGES, required=False)


@extend_schema_field(OpenApiTypes.BINARY)
class PhotoUploadField(serializers.FileField):
    """A bare ``FileField`` documents as ``format: uri``, and generators emit a
    string for it instead of a multipart upload.
    """


class ProfilePhotoSerializer(serializers.Serializer):
    photo = PhotoUploadField()

    def validate_photo(self, photo: Any) -> Any:
        # Size first, so an oversized upload is refused before it is read.
        if photo.size > MAX_PHOTO_BYTES:
            raise ValidationError("The photo is larger than 2 MB.")
        # The type is read from the bytes, so a renamed file is judged by content.
        FileValidator(allowed_mimetypes=PHOTO_TYPES)([photo])
        return photo


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


class CapabilitySerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=CAPABILITY_KEY_VALUES)
    label = serializers.CharField()
    description = serializers.CharField()
    setting = serializers.ChoiceField(choices=CAPABILITY_SETTING_VALUES)
    allowed_for_me = serializers.BooleanField(
        help_text="The setting does not block the caller. The endpoint's own "
        "rules (admin checks, platform-key permission level, ownership) still "
        "apply. Always true for admins and service accounts."
    )
    configurable = serializers.BooleanField(
        help_text="Whether PATCH accepts any_member for this capability. False "
        "while the endpoints it governs still allow only admins; setting "
        "any_member then answers 400."
    )


class CapabilitiesResponseSerializer(serializers.Serializer):
    capabilities = CapabilitySerializer(many=True)


class CapabilitiesPatchSerializer(serializers.Serializer):
    """A ``{capability: setting}`` map; any subset, at least one key.

    Every key and value is checked before anything is saved. A capability
    whose endpoints do not enforce it yet only accepts ``admins_only``.
    """

    def get_fields(self) -> dict[str, serializers.Field]:
        return {
            spec.key.value: serializers.ChoiceField(
                choices=CAPABILITY_SETTING_VALUES, required=False
            )
            for spec in SPECS
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(self.initial_data or {}) - set(SPECS_BY_KEY))
        if unknown:
            raise ValidationError(dict.fromkeys(unknown, "Unknown capability."))
        if not attrs:
            raise ValidationError("Provide at least one capability.")
        not_yet = {
            key: (
                "Not configurable yet: the endpoints it governs still allow "
                "only organisation admins."
            )
            for key, value in attrs.items()
            if value == CapabilitySetting.ANY_MEMBER and not SPECS_BY_KEY[key].enforced
        }
        if not_yet:
            raise ValidationError(not_yet)
        return attrs
