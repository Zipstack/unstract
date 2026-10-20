"""Signed-in sessions of the caller: list them, end one, end all.

Mounted under the organization-scoped `users/` prefix, but a user's sessions
span organizations, so every query filters on the user alone.
"""

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from account_v2.models import SessionRecord
from account_v2.serializer import SignedInSessionSerializer
from account_v2.session_tracking import SessionTracker, parse_user_agent


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
        "location": record.location,
        "last_active": record.last_active_at,
        "created": record.created_at,
        "is_current": record.session_key == current_key,
    }


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revoke_all_sessions(request: Request) -> Response:
    _require_browser_session(request)
    SessionTracker.revoke_all(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def revoke_session(request: Request, session_id: str) -> Response:
    _require_browser_session(request)
    if not SessionTracker.revoke(request, session_id):
        raise NotFound("Session not found.")
    return Response(status=status.HTTP_204_NO_CONTENT)
