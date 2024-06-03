import json
import logging
import os
from datetime import datetime, timezone

from logs_helper.constants import LogsHelperKeys
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from utils.local_context import StateStore
from django_redis import get_redis_connection

from .serializers import StoreLogMessagesSerializer

logger = logging.getLogger(__name__)


class LogsHelperView(viewsets.ModelViewSet):
    """Viewset to handle all Tool Studio prompt related API logics."""

    r = get_redis_connection("default")

    @action(detail=False, methods=["get"])
    def get_logs(self, request):
        # Extract the session ID
        session_id: str = StateStore.get(LogsHelperKeys.LOG_EVENTS_ID)

        # Construct the Redis key pattern to match keys
        # associated with the session ID
        redis_key = f"logs:{session_id}*"

        # Retrieve keys matching the pattern
        keys = self.r.keys(redis_key)

        # Retrieve values corresponding to the keys and sort them by timestamp
        logs = []
        for key in keys:
            log_data = self.r.get(key).decode()
            log_entry = json.loads(log_data)
            logs.append(log_entry)

        # Sort logs based on timestamp
        sorted_logs = sorted(logs, key=lambda x: x["timestamp"])

        return Response({"data": sorted_logs}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def store_log(self, request):
        """Store log message in Redis."""
        # Extract the session ID
        logs_expiry = int(os.environ.get("LOGS_EXPIRATION_TIME_IN_SECOND", 3600))
        session_id: str = StateStore.get(LogsHelperKeys.LOG_EVENTS_ID)

        serializer = StoreLogMessagesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extract the log message from the validated data
        log: str = serializer.validated_data.get("log")

        timestamp = datetime.now(timezone.utc).timestamp()

        redis_key = f"logs:{session_id}:{timestamp}"

        self.r.setex(redis_key, logs_expiry, log)

        return Response({"message": "Successfully stored the message in redis"})
