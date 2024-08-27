from account.authentication_plugin_registry import AuthenticationPluginRegistry
from account.authentication_service import AuthenticationService
from account.constants import Common
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from utils.local_context import StateStore
from utils.user_session import UserSessionUtils

from backend.constants import RequestHeader


class CustomAuthMiddleware:
    def __init__(self, get_response: HttpResponse):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request: HttpRequest) -> HttpResponse:
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
        is_authorized = UserSessionUtils.is_authorized_path(request)

        if is_authenticated and is_authorized:
            StateStore.set(Common.LOG_EVENTS_ID, request.session.session_key)
            response = self.get_response(request)
            StateStore.clear(Common.LOG_EVENTS_ID)

            return response
        return JsonResponse({"message": "Unauthorized"}, status=401)
