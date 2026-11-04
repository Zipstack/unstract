"""Signed-in sessions of the caller: list them, end one, end all.

Mounted under the organization-scoped `users/` prefix, but a user's sessions
span organizations, so every query filters on the user alone.
"""

from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from account_v2.models import SessionRecord
from account_v2.serializer import SignedInSessionSerializer
from account_v2.session_tracking import (
    IdentityProviderError,
    SessionTracker,
    parse_user_agent,
)

NOT_A_BROWSER_SESSION = OpenApiResponse(
    description="Called with a Platform API key or without a session"
)


class IdentityProviderUnavailable(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The identity provider could not end the session. Try again."
    default_code = "identity_provider_unavailable"


def _require_browser_session(request: Request) -> None:
    # A Platform API key authenticates without a session, so it has none to manage.
    if getattr(request, "platform_api_key", None) or not request.session.session_key:
        raise PermissionDenied("Sessions can only be managed from a signed-in browser.")


def _describe(record: SessionRecord, current_key: str) -> dict[str, Any]:
    device = parse_user_agent(record.user_agent)
    return {
        "id": str(record.id),
        "browser": device.browser,
        "os": device.os,
        "device_label": device.label,
        "location": record.location or None,
        "last_active": record.last_active_at,
        "created": record.created_at,
        "is_current": record.session_key == current_key,
    }


@extend_schema(
    operation_id="user_sessions_list",
    tags=["profile"],
    responses={200: SignedInSessionSerializer(many=True), 403: NOT_A_BROWSER_SESSION},
    description=(
        "Where the caller is signed in, across organizations: the current "
        "session first, then by last activity."
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_sessions(request: Request) -> Response:
    _require_browser_session(request)
    current_key = request.session.session_key
    sessions = [
        _describe(record, current_key)
        for record in SessionTracker.live_records(request.user)
    ]
    # Current session first, then most recently active.
    sessions.sort(key=lambda s: (s["is_current"], s["last_active"]), reverse=True)
    sessions.extend(SessionTracker.idp_sessions(request))
    serializer = SignedInSessionSerializer(sessions, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    operation_id="user_sessions_revoke_all",
    tags=["profile"],
    request=None,
    responses={204: None, 403: NOT_A_BROWSER_SESSION},
    description=(
        "Signs the caller out of every session, the current one included. The "
        "response clears the session cookie."
    ),
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revoke_all_sessions(request: Request) -> Response:
    _require_browser_session(request)
    SessionTracker.revoke_all(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    operation_id="user_session_revoke",
    tags=["profile"],
    responses={
        204: None,
        403: NOT_A_BROWSER_SESSION,
        404: OpenApiResponse(description="Not one of the caller's sessions"),
        502: OpenApiResponse(description="The identity provider failed"),
    },
    description=(
        "Signs the caller out of one session. Ending the current one also clears "
        "the session cookie."
    ),
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def revoke_session(request: Request, session_id: str) -> Response:
    _require_browser_session(request)
    try:
        revoked = SessionTracker.revoke(request, session_id)
    except IdentityProviderError as error:
        raise IdentityProviderUnavailable from error
    if not revoked:
        raise NotFound("Session not found.")
    return Response(status=status.HTTP_204_NO_CONTENT)
