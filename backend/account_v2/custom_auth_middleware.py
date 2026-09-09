import hashlib
import logging
import uuid

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from utils.constants import Account
from utils.local_context import StateStore
from utils.user_session import UserSessionUtils

from account_v2.authentication_plugin_registry import AuthenticationPluginRegistry
from account_v2.authentication_service import AuthenticationService
from account_v2.constants import Common
from backend.constants import RequestHeader
from backend.internal_api_constants import INTERNAL_API_PREFIX

logger = logging.getLogger(__name__)


def _client_ip(request: HttpRequest) -> str:
    """Best-effort caller address for a rejection log line."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _log_key_rejection(request: HttpRequest, token: str, reason: str) -> None:
    """Record a rejected Bearer credential without recording the credential.

    The fingerprint is a truncated SHA-256 of the presented token: enough to
    correlate repeated attempts against one candidate, useless for replay.
    """
    fingerprint = hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()[:12]
    logger.warning(
        "Platform key rejected (%s), fingerprint %s, path %s, from %s",
        reason,
        fingerprint,
        request.path,
        _client_ip(request),
    )


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

        # Skip internal API paths - they are handled by InternalAPIAuthMiddleware
        if request.path.startswith(f"{INTERNAL_API_PREFIX}/"):
            return self.get_response(request)

        # Authenticating With API_KEY
        x_api_key = request.headers.get(RequestHeader.X_API_KEY)
        if (
            settings.INTERNAL_SERVICE_API_KEY
            and x_api_key == settings.INTERNAL_SERVICE_API_KEY
        ):  # Should API Key be in settings or just env alone?
            return self.get_response(request)

        # Authenticate with Bearer token (Platform API Key)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return self._authenticate_with_platform_key(request, auth_header)

        if AuthenticationPluginRegistry.is_plugin_available():
            auth_service: AuthenticationService = (
                AuthenticationPluginRegistry.get_plugin()
            )
        else:
            auth_service = AuthenticationService()

        is_authenticated = auth_service.is_authenticated(request)

        if is_authenticated:
            organization_id = UserSessionUtils.get_organization_id(request=request)
            # `request.organization_id` is None on two kinds of path: one with no
            # organisation segment at all, and one matched by
            # ORGANIZATION_MIDDLEWARE_WHITELISTED_PATHS, which sets it to None
            # deliberately. Either way this guard does not run, so a route added
            # to that whitelist loses this check as well as the Bearer branch's
            # -- see the note beside the setting.
            if request.organization_id and not organization_id:
                return JsonResponse({"message": "Organization access denied"}, status=403)
            StateStore.set(Common.LOG_EVENTS_ID, request.session.session_key)
            StateStore.set(Account.ORGANIZATION_ID, organization_id)
            response = self.get_response(request)
            StateStore.clear(Account.ORGANIZATION_ID)
            StateStore.clear(Common.LOG_EVENTS_ID)

            return response
        return JsonResponse({"message": "Unauthorized"}, status=401)

    def _authenticate_with_platform_key(
        self, request: HttpRequest, auth_header: str
    ) -> HttpResponse:
        """Authenticate request using a Platform API Key Bearer token.

        Resolves the token to the owning user so all downstream code sees
        a fully authenticated request.
        """
        from platform_api.models import ApiKeyPermission, PlatformApiKey

        token_str = auth_header[len("Bearer ") :]
        try:
            key_uuid = uuid.UUID(token_str)
        except (ValueError, AttributeError):
            # Logged like the branch below: these two are the ones an attacker
            # traverses, and until now neither left a trace, so "was this key
            # ever presented?" had no data to answer from. The token is never
            # logged -- only a truncated SHA-256, which is enough to correlate
            # repeated attempts against one candidate without storing it.
            _log_key_rejection(request, token_str, "malformed key")
            return JsonResponse({"message": "Invalid API key format"}, status=401)

        try:
            key = PlatformApiKey.objects.select_related(
                "created_by", "api_user", "organization"
            ).get(key=key_uuid, is_active=True)
        except PlatformApiKey.DoesNotExist:
            _log_key_rejection(request, token_str, "unknown or inactive key")
            return JsonResponse({"message": "Invalid or inactive API key"}, status=401)

        # Validate the key belongs to the org in the URL
        if request.organization_id and str(key.organization.organization_id) != str(
            request.organization_id
        ):
            # The highest-signal security event in this file: a valid key aimed
            # at an organisation it does not belong to.
            logger.warning(
                "Platform key %s (org %s) refused for org %s from %s",
                key.id,
                key.organization.organization_id,
                request.organization_id,
                _client_ip(request),
            )
            return JsonResponse(
                {"message": "API key does not belong to this organization"},
                status=403,
            )

        if not key.api_user:
            logger.error("API key %s has no linked service account", key.id)
            return JsonResponse(
                {
                    "message": "API key service account is missing. "
                    "Please delete and recreate the key."
                },
                status=401,
            )

        if key.permission not in ApiKeyPermission.values:
            logger.error(
                "API key %s has unrecognized permission tier %r",
                key.id,
                key.permission,
            )
            return JsonResponse(
                {"message": "API key has an unrecognized permission tier"},
                status=403,
            )

        permission = ApiKeyPermission(key.permission)
        if not permission.allows(request.method):
            return JsonResponse(
                {
                    "message": (
                        f"API key with permission '{permission.value}' "
                        f"does not allow {request.method}"
                    )
                },
                status=403,
            )

        request.user = key.api_user
        request.platform_api_key = key
        # Skip CSRF for Bearer-authenticated requests
        request.csrf_processing_done = True
        StateStore.set(Common.LOG_EVENTS_ID, str(key.id))
        StateStore.set(Account.ORGANIZATION_ID, key.organization.organization_id)

        try:
            return self.get_response(request)
        finally:
            StateStore.clear(Account.ORGANIZATION_ID)
            StateStore.clear(Common.LOG_EVENTS_ID)
