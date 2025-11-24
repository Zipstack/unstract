"""WebSocket consumers for real-time progress updates."""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class ProgressConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for pipeline progress updates."""

    async def connect(self):
        """Handle WebSocket connection."""
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]
        self.room_group_name = f"agentic_progress_{self.project_id}"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()
        logger.info(f"WebSocket connected for project {self.project_id}")

        # Send connection confirmation
        await self.send(
            text_data=json.dumps(
                {"type": "connection", "status": "connected", "project_id": self.project_id}
            )
        )

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        logger.info(f"WebSocket disconnected for project {self.project_id}, code: {close_code}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages (heartbeat)."""
        try:
            data = json.loads(text_data)
            if data.get("type") == "ping":
                await self.send(text_data=json.dumps({"type": "pong"}))
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    async def progress_update(self, event):
        """Send progress update to WebSocket.

        This method is called when a message is sent to the channel layer group.
        """
        await self.send(text_data=json.dumps(event["data"]))
