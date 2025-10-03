"""Internal API Service Authentication Middleware
Handles service-to-service authentication for internal APIs.
"""

import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from utils.constants import Account
from utils.local_context import StateStore

logger = logging.getLogger(__name__)


class InternalAPIAuthMiddleware(MiddlewareMixin):
    """Middleware for authenticating internal service API requests.

    This middleware:
    1. Checks for internal service API key in Authorization header
    2. Validates the key against INTERNAL_SERVICE_API_KEY setting
    3. Sets up organization context for requests
    4. Bypasses normal user authentication for internal services
    """

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        """Enhanced request processing with improved debugging and organization context handling."""
        # Enhanced request logging with more context
        request_info = {
            "path": request.path,
            "method": request.method,
            "content_type": request.META.get("CONTENT_TYPE", "unknown"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "unknown")[:100],
            "remote_addr": request.META.get("REMOTE_ADDR", "unknown"),
            "auth_header_present": bool(request.META.get("HTTP_AUTHORIZATION")),
            "org_header_present": bool(request.headers.get("X-Organization-ID")),
        }

        logger.debug(f"InternalAPIAuthMiddleware processing request: {request_info}")

        # Only apply to internal API endpoints
        if not request.path.startswith("/internal/"):
            logger.debug(f"Skipping middleware for non-internal path: {request.path}")
            return None

        logger.info(f"Processing internal API request: {request.method} {request.path}")

        # Enhanced authentication handling
        auth_result = self._authenticate_request(request)
        if auth_result["error"]:
            logger.warning(
                f"Authentication failed for {request.path}: {auth_result['message']}"
            )
            return JsonResponse(
                {
                    "error": auth_result["message"],
                    "detail": auth_result["detail"],
                    "debug_info": auth_result.get("debug_info", {})
                    if settings.DEBUG
                    else {},
                },
                status=auth_result["status"],
            )

        # Enhanced organization context handling
        org_result = self._setup_organization_context(request)
        if org_result["warning"]:
            logger.warning(
                f"Organization context issue for {request.path}: {org_result['warning']}"
            )

        # Mark request as authenticated
        request.internal_service = True
        request.authenticated_via = "internal_service_api_key"

        # Enhanced organization context logging
        final_context = {
            "path": request.path,
            "request_org_id": getattr(request, "organization_id", "None"),
            "statestore_org_id": StateStore.get(Account.ORGANIZATION_ID),
            "org_context_set": org_result["context_set"],
            "org_validated": org_result.get("organization_validated", False),
        }
        logger.info(f"Internal API request authenticated successfully: {final_context}")
        return None  # Continue with request processing

    def _authenticate_request(self, request: HttpRequest) -> dict[str, Any]:
        """Enhanced authentication with detailed error reporting."""
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header:
            return {
                "error": True,
                "status": 401,
                "message": "Authorization header required for internal APIs",
                "detail": "Missing Authorization header",
                "debug_info": {
                    "headers_present": list(request.META.keys()),
                    "expected_format": "Authorization: Bearer <api_key>",
                },
            }

        if not auth_header.startswith("Bearer "):
            return {
                "error": True,
                "status": 401,
                "message": "Bearer token required for internal APIs",
                "detail": f"Invalid authorization format: {auth_header[:20]}...",
                "debug_info": {
                    "provided_format": auth_header.split(" ")[0]
                    if " " in auth_header
                    else auth_header[:10],
                    "expected_format": "Bearer <api_key>",
                },
            }

        # Extract and validate API key
        api_key = auth_header[7:]  # Remove 'Bearer ' prefix
        internal_api_key = getattr(settings, "INTERNAL_SERVICE_API_KEY", None)

        if not internal_api_key:
            logger.error("INTERNAL_SERVICE_API_KEY not configured in Django settings")
            return {
                "error": True,
                "status": 500,
                "message": "Internal API authentication not configured",
                "detail": "INTERNAL_SERVICE_API_KEY setting missing",
            }

        if api_key != internal_api_key:
            # Enhanced logging for key mismatch debugging
            key_comparison = {
                "provided_key_length": len(api_key),
                "expected_key_length": len(internal_api_key),
                "keys_match": api_key == internal_api_key,
                "provided_key_prefix": api_key[:8] + "..."
                if len(api_key) > 8
                else api_key,
                "expected_key_prefix": internal_api_key[:8] + "..."
                if len(internal_api_key) > 8
                else internal_api_key,
            }
            logger.warning(f"API key validation failed: {key_comparison}")

            return {
                "error": True,
                "status": 401,
                "message": "Invalid internal service API key",
                "detail": "API key does not match configured value",
                "debug_info": key_comparison if settings.DEBUG else {},
            }

        return {"error": False, "message": "Authentication successful"}

    def _setup_organization_context(self, request: HttpRequest) -> dict[str, Any]:
        """Enhanced organization context setup with validation."""
        org_id = request.headers.get("X-Organization-ID")

        if not org_id:
            return {
                "warning": "No organization ID provided in X-Organization-ID header",
                "context_set": False,
            }

        try:
            # Validate organization ID format
            if not org_id.strip():
                return {"warning": "Empty organization ID provided", "context_set": False}

            # Enhanced organization context validation
            from utils.organization_utils import resolve_organization

            try:
                organization = resolve_organization(org_id, raise_on_not_found=False)
                if organization:
                    # Use organization.organization_id (string field) for StateStore consistency
                    # This ensures UserContext.get_organization() can properly retrieve the organization
                    request.organization_id = organization.organization_id
                    request.organization_context = {
                        "id": str(organization.id),
                        "organization_id": organization.organization_id,
                        "name": organization.display_name,
                        "validated": True,
                    }
                    # Store the organization_id string field in StateStore for UserContext compatibility
                    StateStore.set(Account.ORGANIZATION_ID, organization.organization_id)

                    logger.debug(
                        f"Organization context validated and set: {organization.display_name} (org_id: {organization.organization_id}, pk: {organization.id})"
                    )
                    return {
                        "warning": None,
                        "context_set": True,
                        "organization_validated": True,
                    }
                else:
                    logger.warning(f"Organization {org_id} not found in database")
                    # Still set the context for backward compatibility
                    request.organization_id = org_id
                    StateStore.set(Account.ORGANIZATION_ID, org_id)
                    return {
                        "warning": f"Organization {org_id} not found in database, using raw value",
                        "context_set": True,
                        "organization_validated": False,
                    }

            except Exception as e:
                logger.warning(f"Failed to validate organization {org_id}: {str(e)}")
                # Fallback to raw organization ID
                request.organization_id = org_id
                StateStore.set(Account.ORGANIZATION_ID, org_id)
                return {
                    "warning": f"Organization validation failed: {str(e)}, using raw value",
                    "context_set": True,
                    "organization_validated": False,
                }

        except Exception as e:
            logger.error(f"Unexpected error setting organization context: {str(e)}")
            return {
                "warning": f"Failed to set organization context: {str(e)}",
                "context_set": False,
            }

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        # Clean up organization context if we set it
        if hasattr(request, "internal_service") and request.internal_service:
            try:
                org_id_before_clear = StateStore.get(Account.ORGANIZATION_ID)
                if org_id_before_clear is not None:
                    StateStore.clear(Account.ORGANIZATION_ID)
                    logger.debug(
                        f"Cleaned up organization context for {request.path}: {org_id_before_clear}"
                    )
            except AttributeError:
                # StateStore key doesn't exist, which is fine
                logger.debug(f"No organization context to clean up for {request.path}")
        return response
