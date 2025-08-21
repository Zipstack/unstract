"""WebSocket emission views for internal API.

This module provides endpoints for workers to trigger WebSocket events
through the backend's SocketIO server.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from utils.log_events import _emit_websocket_event

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def emit_websocket(request):
    """Internal API endpoint for workers to emit WebSocket events.

    Expected payload:
    {
        "room": "session_id",
        "event": "logs:session_id",
        "data": {...}
    }

    Returns:
        JSON response with success/error status
    """
    try:
        # Parse request data (standard Django view)
        data = json.loads(request.body.decode("utf-8"))

        # Extract required fields
        room = data.get("room")
        event = data.get("event")
        message_data = data.get("data", {})

        # Validate required fields
        if not room or not event:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Missing required fields: room and event are required",
                },
                status=400,
            )

        # Emit the WebSocket event
        _emit_websocket_event(room=room, event=event, data=message_data)

        logger.debug(f"WebSocket event emitted: room={room}, event={event}")

        return JsonResponse(
            {
                "status": "success",
                "message": "WebSocket event emitted successfully",
                "room": room,
                "event": event,
            }
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in WebSocket emission request: {e}")
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON payload"}, status=400
        )
    except Exception as e:
        logger.error(f"Error emitting WebSocket event: {e}")
        return JsonResponse(
            {"status": "error", "message": f"Failed to emit WebSocket event: {str(e)}"},
            status=500,
        )
