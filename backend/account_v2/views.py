import logging
from typing import Any

from django.conf import settings
from django.http.response import HttpResponseBase, HttpResponseRedirectBase
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_session import UserSessionUtils

from account_v2.authentication_controller import AuthenticationController
from account_v2.dto import (
    OrganizationSignupRequestBody,
    OrganizationSignupResponse,
    UserSessionInfo,
)
from account_v2.models import Organization
from account_v2.organization import OrganizationService
from account_v2.product_preference import (
    get_product_preference,
    set_product_preference,
)
from account_v2.serializer import (
    GetOrganizationsResponseSerializer,
    OrganizationSignupResponseSerializer,
    OrganizationSignupSerializer,
    ProductPreferenceSerializer,
    ProductPreferenceUpdateSerializer,
    UserSessionResponseSerializer,
)

Logger = logging.getLogger(__name__)


@api_view(["POST"])
def create_organization(request: Request) -> Response:
    serializer = OrganizationSignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        requestBody: OrganizationSignupRequestBody = makeSignupRequestParams(serializer)

        organization: Organization = OrganizationService.create_organization(
            requestBody.name,
            requestBody.display_name,
            requestBody.organization_id,
        )
        response = makeSignupResponse(organization)
        return Response(
            status=status.HTTP_201_CREATED,
            data={"message": "success", "tenant": response},
        )
    except Exception as error:
        Logger.error(error)
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR, data="Unknown Error"
        )


@api_view(["GET"])
def callback(request: Request) -> Response:
    auth_controller = AuthenticationController()
    return auth_controller.authorization_callback(request)


@api_view(["GET", "POST"])
def login(request: Request) -> Response:
    auth_controller = AuthenticationController()
    return auth_controller.user_login(request)


@api_view(["GET"])
def signup(request: Request) -> Response:
    auth_controller = AuthenticationController()
    return auth_controller.user_signup(request)


# POST is the CSRF-protected sign-out for v1. GET stays for v0's useLogout and
# can go once v0 is retired.
@api_view(["GET", "POST"])
def logout(request: Request) -> HttpResponseBase:
    auth_controller = AuthenticationController()
    response = auth_controller.user_logout(request)
    if request.method == "POST" and isinstance(response, HttpResponseRedirectBase):
        # A fetch or XHR caller cannot follow the cross-origin redirect a cloud
        # sign-out ends in, so POST returns the target for the client to open.
        payload = Response({"redirect_url": response.url})
        payload.cookies.update(response.cookies)
        return payload
    return response


@extend_schema(
    operation_id="organization_list",
    tags=["organization"],
    responses={
        200: inline_serializer(
            "OrganizationListResponse",
            {
                "message": serializers.CharField(),
                "organizations": GetOrganizationsResponseSerializer(many=True),
            },
        ),
        412: OpenApiResponse(
            # Describes the body for a known error, which always carries both
            # keys; for any other error the body is empty, as the description
            # says. One OpenAPI response can't express both.
            response=inline_serializer(
                "OrganizationListFailed",
                {
                    "domain": serializers.CharField(allow_null=True),
                    "code": serializers.CharField(),
                },
            ),
            description="Listing the organizations failed and the session is "
            "logged out. For a known authorization error the body carries "
            "`code` (USF, USR, INE001, INE002 or INS) and `domain`; otherwise "
            "it is empty.",
        ),
    },
    description="The caller's organizations. See account_v2/ReadMe.md for "
    "when role, member_count and region are present.",
)
@api_view(["GET"])
def get_organizations(request: Request) -> Response:
    """get_organizations.

    Retrieve the list of organizations to which the user belongs.

    Args:
        request (HttpRequest): _description_

    Returns:
        Response: A list of organizations with associated information.
    """
    auth_controller = AuthenticationController()
    return auth_controller.user_organizations(request)


@api_view(["POST"])
def set_organization(request: Request, id: str) -> Response:
    """set_organization.

    Set the current organization to use.

    Args:
        request (HttpRequest): _description_
        id (String): organization Id

    Returns:
        Response: Contains the User and Current organization details.
    """
    auth_controller = AuthenticationController()
    return auth_controller.set_user_organization(request, id)


@api_view(["GET"])
def get_session_data(request: Request) -> Response:
    """get_session_data.

    Retrieve the current session data.

    Args:
        request (HttpRequest): _description_

    Returns:
        Response: Contains the User and Current organization details.
    """
    response = make_session_response(request)

    return Response(
        status=status.HTTP_201_CREATED,
        data=response,
    )


def make_session_response(
    request: Request,
) -> Any:
    """make_session_response.

    Make the current session data.

    Args:
        request (HttpRequest): _description_

    Returns:
        User and Current organization details.
    """
    auth_controller = AuthenticationController()
    token_data = UserSessionUtils.get_token_data(request)
    provider = "" if token_data is None else token_data.get("provider", "")
    # Not guarded: a failed read must not pass for "never chosen", which
    # would send a returning user through the first-login choice.
    preference = get_product_preference(request.user)
    return UserSessionResponseSerializer(
        UserSessionInfo(
            id=request.user.id,
            user_id=request.user.user_id,
            email=request.user.email,
            user=auth_controller.get_user_info(request),
            organization_id=UserSessionUtils.get_organization_id(request),
            role=UserSessionUtils.get_organization_member_role(request),
            provider=provider,
            is_staff=request.user.is_staff,
            disable_sso_idp_authorization=settings.DISABLE_SSO_IDP_AUTHORIZATION,
            last_product=preference.product,
            has_chosen=preference.has_chosen,
        )
    ).data


@api_view(["GET", "PUT"])
def product_preference(request: Request) -> Response:
    """Read or write the signed-in user's last-used product.

    The preference belongs to the user, not the organisation, so this route
    carries no organisation segment and needs none selected: it answers on
    first login, before the user has picked an organisation. A user only
    ever reaches their own row, since the row is looked up from
    ``request.user``. Service accounts (platform API keys) are refused, as
    they never land anywhere.
    """
    if getattr(request.user, "is_service_account", False):
        return Response(
            status=status.HTTP_403_FORBIDDEN,
            data={"message": "Service accounts have no product preference"},
        )
    if request.method == "PUT":
        serializer = ProductPreferenceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preference = set_product_preference(
            request.user, serializer.validated_data["product"]
        )
    else:
        preference = get_product_preference(request.user)
    return Response(
        status=status.HTTP_200_OK, data=ProductPreferenceSerializer(preference).data
    )


def makeSignupRequestParams(
    serializer: OrganizationSignupSerializer,
) -> OrganizationSignupRequestBody:
    return OrganizationSignupRequestBody(
        serializer.validated_data["name"],
        serializer.validated_data["display_name"],
        serializer.validated_data["organization_id"],
    )


def makeSignupResponse(
    organization: Organization,
) -> Any:
    return OrganizationSignupResponseSerializer(
        OrganizationSignupResponse(
            organization.name,
            organization.display_name,
            organization.organization_id,
            organization.created_at,
        )
    ).data
