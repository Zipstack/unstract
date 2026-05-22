import logging
from typing import Any

from account_v2.authentication_controller import AuthenticationController
from account_v2.dto import UserRoleData
from account_v2.models import Organization
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_session import UserSessionUtils

from tenant_account_v2.dto import OrganizationLoginResponse, ResetUserPasswordDto
from tenant_account_v2.serializer import (
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


@api_view(["GET", "PATCH"])
def get_organization(request: Request) -> Response:
    if request.method == "PATCH":
        return _patch_organization(request)
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
        response["idp_group_allowlist"] = list(
            getattr(org_data, "idp_group_allowlist", None) or []
        )
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


def _patch_organization(request: Request) -> Response:
    """Org-admin-only updates to the current Organization row.

    Phase 1 only writes ``idp_group_allowlist``; other fields are out of scope.
    """
    from platform_api.permissions import IsOrganizationAdmin

    if not IsOrganizationAdmin().has_permission(request, None):
        return Response(
            status=status.HTTP_403_FORBIDDEN,
            data={"message": "Only organization admins can update this resource."},
        )
    allowlist = request.data.get("idp_group_allowlist")
    if allowlist is None or not isinstance(allowlist, list):
        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data={"message": "idp_group_allowlist must be a list of strings."},
        )
    cleaned = _validate_allowlist(allowlist)
    if isinstance(cleaned, Response):
        return cleaned

    organization_id = UserSessionUtils.get_organization_id(request)
    try:
        organization = Organization.objects.get(organization_id=organization_id)
    except Organization.DoesNotExist:
        return Response(
            status=status.HTTP_404_NOT_FOUND,
            data={"message": "Org Not Found"},
        )
    organization.idp_group_allowlist = cleaned
    organization.save(update_fields=["idp_group_allowlist", "modified_at"])
    return Response(
        status=status.HTTP_200_OK,
        data={"message": "success", "idp_group_allowlist": cleaned},
    )


def _validate_allowlist(allowlist: list[Any]) -> list[str] | Response:
    cleaned: list[str] = []
    for entry in allowlist:
        if not isinstance(entry, str):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"message": "idp_group_allowlist entries must be strings."},
            )
        trimmed = entry.strip()
        if not trimmed:
            continue
        if len(trimmed) > 256:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    "message": (
                        "idp_group_allowlist entries must be 256 characters or fewer."
                    )
                },
            )
        cleaned.append(trimmed)
    # Dedupe while preserving order.
    return list(dict.fromkeys(cleaned))


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
