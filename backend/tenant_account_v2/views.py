import logging
from typing import Any

from account_v2.authentication_controller import AuthenticationController
from account_v2.dto import UserRoleData
from account_v2.models import Organization
from platform_api.permissions import IsOrganizationAdmin
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_context import UserContext
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
        for flag, value in provided.items():
            if not isinstance(value, bool):
                return Response(
                    status=status.HTTP_400_BAD_REQUEST,
                    data={"message": f"{flag} must be a boolean"},
                )
            setattr(organization, flag, value)
        organization.modified_by = request.user
        organization.save(update_fields=[*provided, "modified_by", "modified_at"])

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
