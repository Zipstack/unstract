import logging
from typing import Any

from account.authentication_controller import AuthenticationController
from account.dto import UserRoleData
from account.models import Organization
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from tenant_account.dto import OrganizationLoginResponse, ResetUserPasswordDto
from tenant_account.serializer import (
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


@api_view(["GET"])
def get_organization(request: Request) -> Response:
    auth_controller = AuthenticationController()
    try:
        org_data = auth_controller.get_organization_info(request.org_id)
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
        logger.error(f"Error while get User : {error}")
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
