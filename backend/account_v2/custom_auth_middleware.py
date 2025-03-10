from account_v2.authentication_plugin_registry import AuthenticationPluginRegistry
from account_v2.authentication_service import AuthenticationService
from account_v2.constants import Common
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from utils.constants import Account
from utils.local_context import StateStore
from utils.user_session import UserSessionUtils

from backend.constants import RequestHeader


class CustomAuthMiddleware:
    def __init__(self, get_response: HttpResponse):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Add request_id in StateStore
        StateStore.set(Common.REQUEST_ID, request.id)
        # Returns result without authenticated if added in whitelisted paths
        if any(request.path.startswith(path) for path in settings.WHITELISTED_PATHS):
            return self.get_response(request)

        # Authenticating With API_KEY
        x_api_key = request.headers.get(RequestHeader.X_API_KEY)
        if (
            settings.INTERNAL_SERVICE_API_KEY
            and x_api_key == settings.INTERNAL_SERVICE_API_KEY
        ):  # Should API Key be in settings or just env alone?
            return self.get_response(request)

        if AuthenticationPluginRegistry.is_plugin_available():
            auth_service: AuthenticationService = (
                AuthenticationPluginRegistry.get_plugin()
            )
        else:
            auth_service = AuthenticationService()

        is_authenticated = auth_service.is_authenticated(request)

        if is_authenticated:
            StateStore.set(Common.LOG_EVENTS_ID, request.session.session_key)
            StateStore.set(
                Account.ORGANIZATION_ID,
                UserSessionUtils.get_organization_id(request=request),
            )
            response = self.get_response(request)
            StateStore.clear(Account.ORGANIZATION_ID)
            StateStore.clear(Common.LOG_EVENTS_ID)

            return response
        return JsonResponse({"message": "Unauthorized"}, status=401)
