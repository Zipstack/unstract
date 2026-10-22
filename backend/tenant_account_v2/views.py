import logging
from typing import Any

from account_v2.authentication_controller import AuthenticationController
from account_v2.dto import UserRoleData
from account_v2.models import Organization
from django.db import transaction
from drf_spectacular.utils import extend_schema
from drf_standardized_errors.openapi_serializers import (
    ErrorResponse403Serializer,
    ErrorResponse404Serializer,
    ValidationErrorResponseSerializer,
)
from platform_api.permissions import IsOrganizationAdmin
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import best_effort, record_platform_event
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_context import UserContext
from utils.user_session import UserSessionUtils

from tenant_account_v2.capabilities import (
    SPECS,
    SPECS_BY_KEY,
    CapabilitySetting,
    is_allowed,
    setting_of,
)
from tenant_account_v2.dto import OrganizationLoginResponse, ResetUserPasswordDto
from tenant_account_v2.serializer import (
    CapabilitiesPatchSerializer,
    CapabilitiesResponseSerializer,
    GetRolesResponseSerializer,
    OrganizationLoginResponseSerializer,
)

logger = logging.getLogger(__name__)


@api_view(["GET"])
def logout(request: Request) -> Response:
    auth_controller = AuthenticationController()
    return auth_controller.user_logout(request)


@api_view(["GET"])
def get_roles(request: Request) -> Response:
    auth_controller = AuthenticationController()
    roles: list[UserRoleData] = auth_controller.get_user_roles()
    serialized_members = GetRolesResponseSerializer(roles, many=True).data
    return Response(
        status=status.HTTP_200_OK,
        data={"message": "success", "members": serialized_members},
    )


@api_view(["POST"])
def reset_password(request: Request) -> Response:
    auth_controller = AuthenticationController()
    data: ResetUserPasswordDto = auth_controller.reset_user_password(request.user)
    if data.status:
        return Response(
            status=status.HTTP_200_OK,
            data={"status": "success", "message": data.message},
        )
    else:
        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data={"status": "failed", "message": data.message},
        )


# Boolean org-level controlled-mode flags exposed by ``organization_settings``.
# Each maps a request/response key to the ``Organization`` field it updates.
ORGANIZATION_SETTING_FLAGS = (
    "restrict_llm_adapter_creation",
    "restrict_connector_creation",
)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsOrganizationAdmin])
def organization_settings(request: Request) -> Response:
    """Read or update org-level settings. Admin-only.

    Exposes the controlled-mode flags in ``ORGANIZATION_SETTING_FLAGS``
    (``restrict_llm_adapter_creation``, ``restrict_connector_creation``). GET
    returns the current values; PATCH updates any subset of them.
    """
    organization = UserContext.get_organization()
    if not organization:
        return Response(
            status=status.HTTP_404_NOT_FOUND,
            data={"message": "Org Not Found"},
        )

    if request.method == "PATCH":
        provided = {
            flag: request.data[flag]
            for flag in ORGANIZATION_SETTING_FLAGS
            if flag in request.data
        }
        if not provided:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    "message": (
                        "Provide at least one of: "
                        f"{', '.join(ORGANIZATION_SETTING_FLAGS)}"
                    )
                },
            )
        # Validate everything before mutating so a bad value in a later flag
        # doesn't leave the in-memory org partially updated.
        for flag, value in provided.items():
            if not isinstance(value, bool):
                return Response(
                    status=status.HTTP_400_BAD_REQUEST,
                    data={"message": f"{flag} must be a boolean"},
                )
        organization, before = _save_restrictions(request, organization, provided)
        # These flags are the storage of two capabilities, so a change here is
        # recorded as that capability changing, once, as from the new endpoint.
        _record_capability_changes(request, organization, before)

    return Response(
        status=status.HTTP_200_OK,
        data={flag: getattr(organization, flag) for flag in ORGANIZATION_SETTING_FLAGS},
    )


@api_view(["GET"])
def get_organization(request: Request) -> Response:
    auth_controller = AuthenticationController()
    try:
        organization_id = UserSessionUtils.get_organization_id(request)
        org_data = auth_controller.get_organization_info(organization_id)
        if not org_data:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"message": "Org Not Found"},
            )
        response = makeSignupResponse(org_data)
        return Response(
            status=status.HTTP_201_CREATED,
            data={"message": "success", "organization": response},
        )

    except Exception as error:
        logger.error("Error while get User : %s", error)
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data={"message": "Internal Error"},
        )


def makeSignupResponse(
    organization: Organization,
) -> Any:
    return OrganizationLoginResponseSerializer(
        OrganizationLoginResponse(
            organization.name,
            organization.display_name,
            organization.organization_id,
            organization.created_at,
        )
    ).data


def _capabilities_payload(request: Request, organization: Organization) -> dict:
    return {
        "capabilities": [
            {
                "key": spec.key.value,
                "label": spec.label,
                "description": spec.description,
                "setting": setting_of(organization, spec).value,
                "allowed_for_me": is_allowed(request.user, organization, spec.key),
                "configurable": spec.enforced,
            }
            for spec in SPECS
        ]
    }


@extend_schema(
    methods=["GET"],
    operation_id="organization_capabilities_retrieve",
    tags=["organization-capabilities"],
    responses={
        200: CapabilitiesResponseSerializer,
        403: ErrorResponse403Serializer,
        404: ErrorResponse404Serializer,
    },
    description="Every capability, its setting, and whether it lets the caller "
    "use it. Any member may read it.",
)
@extend_schema(
    methods=["PATCH"],
    operation_id="organization_capabilities_partial_update",
    tags=["organization-capabilities"],
    request=CapabilitiesPatchSerializer,
    responses={
        200: CapabilitiesResponseSerializer,
        400: ValidationErrorResponseSerializer,
        403: ErrorResponse403Serializer,
        404: ErrorResponse404Serializer,
    },
    description="Set any subset of capabilities. Organisation admins only. "
    "Every key and value is validated before anything is saved.",
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def organization_capabilities(request: Request) -> Response:
    """Read capability settings (any member) or change them (admins only)."""
    organization = UserContext.get_organization()
    if not organization:
        raise NotFound("Organization not found.")
    if request.method == "PATCH":
        if not IsOrganizationAdmin().has_permission(request, None):
            raise PermissionDenied(
                "Only organization admins can change capability settings."
            )
        serializer = CapabilitiesPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = {
            SPECS_BY_KEY[key].field: value == CapabilitySetting.ADMINS_ONLY
            for key, value in serializer.validated_data.items()
        }
        organization, before = _save_restrictions(request, organization, changed)
        _record_capability_changes(request, organization, before)
    return Response(
        status=status.HTTP_200_OK, data=_capabilities_payload(request, organization)
    )


def _save_restrictions(
    request: Request, organization: Organization, values: dict[str, bool]
) -> tuple[Organization, dict[str, bool]]:
    """Save ``restrict_*`` fields and return the row with its values before.

    The row is locked while it is read and written, so of two concurrent
    changes the second sees the first's result as its "before" and the audit
    records every change. Both settings endpoints write through here.
    """
    with transaction.atomic():
        locked = Organization.objects.select_for_update().get(pk=organization.pk)
        before = {field: getattr(locked, field) for field in values}
        for field, value in values.items():
            setattr(locked, field, value)
        locked.modified_by = request.user
        locked.save(update_fields=[*values, "modified_by", "modified_at"])
    return locked, before


@best_effort
def _record_capability_changes(
    request: Request, organization: Organization, before: dict[str, bool]
) -> None:
    """One ``capability.changed`` per capability whose setting changed."""
    for spec in SPECS:
        if spec.field not in before:
            continue
        old = _as_setting(before[spec.field])
        new = setting_of(organization, spec).value
        if old == new:
            continue
        record_platform_event(
            action=Action.CAPABILITY_CHANGED,
            target_type=TargetType.CAPABILITY,
            target_id=spec.key.value,
            target_name=spec.label,
            changes={"before": {"setting": old}, "after": {"setting": new}},
            summary=f"{old} → {new}",
            request=request,
            organization=organization,
        )


def _as_setting(restricted: bool) -> str:
    return (
        CapabilitySetting.ADMINS_ONLY if restricted else CapabilitySetting.ANY_MEMBER
    ).value
