from account.authentication_plugin_registry import AuthenticationPluginRegistry
from account.constants import Common, Cookie, DefaultOrg
from account.dto import UserSessionInfo
from account.user import UserService
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from tenant_account.organization_member_service import OrganizationMemberService
from utils.cache_service import CacheService
from utils.local_context import StateStore

from backend.constants import RequestHeader


class CustomAuthMiddleware:
    def __init__(self, get_response: HttpResponse):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Returns result without authenticated if added in whitelisted paths
        if any(
            request.path.startswith(path) for path in settings.WHITELISTED_PATHS
        ):
            return self.get_response(request)

        tenantAccessiblePublicPath = False
        if any(
            request.path.startswith(path)
            for path in settings.TENANT_ACCESSIBLE_PUBLIC_PATHS
        ):
            tenantAccessiblePublicPath = True

        # Authenticating With API_KEY
        x_api_key = request.headers.get(RequestHeader.X_API_KEY)
        if (
            settings.INTERNAL_SERVICE_API_KEY
            and x_api_key == settings.INTERNAL_SERVICE_API_KEY
        ):  # Should API Key be in settings or just env alone?
            return self.get_response(request)

        if not AuthenticationPluginRegistry.is_plugin_available():
            self.local_authentication(request)
        elif request.COOKIES:
            self.authenticate_with_cookies(request, tenantAccessiblePublicPath)
        if request.user and request.session and "user" in request.session:
            StateStore.set(Common.LOG_EVENTS_ID, request.session.session_key)
            response = self.get_response(request)
            StateStore.clear(Common.LOG_EVENTS_ID)

            return response
        return JsonResponse({"message": "Unauthorized"}, status=401)

    def local_authentication(self, request: HttpRequest) -> None:
        org_id = DefaultOrg.MOCK_ORG
        if not request.user.is_authenticated:
            return
        user_session_info = CacheService.get_user_session_info(
            request.user.email
        )
        if not user_session_info:
            user_info: UserSessionInfo = UserSessionInfo(
                id=request.user.id,
                user_id=request.user.user_id,
                email=request.user.email,
                current_org=org_id,
            )
            CacheService.set_user_session_info(user_info)
            user_session_info = CacheService.get_user_session_info(
                request.user.email
            )
        request.org_id = org_id
        request.session["user"] = user_session_info
        request.session.save()

    def authenticate_with_cookies(
        self,
        request: HttpRequest,
        tenantAccessiblePublicPath: bool,
    ) -> None:
        z_code: str = request.COOKIES.get(Cookie.Z_CODE)
        token = cache.get(z_code) if z_code else None
        if not token:
            return

        user_email = token["userinfo"]["email"]
        user_session_info = CacheService.get_user_session_info(user_email)
        if not user_session_info:
            return

        current_org = user_session_info["current_org"]
        if not current_org:
            return

        if (
            current_org != connection.get_schema()
            and not tenantAccessiblePublicPath
        ):
            return

        if (
            current_org == Common.PUBLIC_SCHEMA_NAME
            or tenantAccessiblePublicPath
        ):
            user_service = UserService()
        else:
            organization_member_service = OrganizationMemberService()
            member = organization_member_service.get_user_by_email(user_email)
            if not member:
                return
            user_service = UserService()

        user = user_service.get_user_by_email(user_email)

        if not user:
            return

        request.user = user
        request.org_id = current_org
        request.session["user"] = token
        request.session.save()
