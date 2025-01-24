import json
import logging
from datetime import datetime, timezone

from django.conf import settings
from django.http import HttpRequest
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from utils.cache_service import CacheService
from utils.user_session import UserSessionUtils

from .log_service import LogService
from .serializers import StoreLogMessagesSerializer

logger = logging.getLogger(__name__)


class LogsHelperViewSet(viewsets.ModelViewSet):
    """Viewset to handle all Tool Studio prompt related API logics."""

    @action(detail=False, methods=["get"])
    def get_logs(self, request: HttpRequest) -> Response:
        # Extract the session ID
        session_id: str = UserSessionUtils.get_session_id(request=request)

        # Construct the Redis key pattern to match keys
        # associated with the session ID
        redis_key = LogService.generate_redis_key(session_id=session_id)

        # Retrieve keys matching the pattern
        keys = CacheService.get_all_keys(f"{redis_key}*")

        # Retrieve values corresponding to the keys and sort them by timestamp
        logs = []
        for key in keys:
            log_data = CacheService.get_key(key)
            logs.append(log_data)

        # Sort logs based on timestamp
        sorted_logs = sorted(logs, key=lambda x: x["timestamp"])

        return Response({"data": sorted_logs}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def store_log(self, request: HttpRequest) -> Response:
        """Store log message in Redis."""
        # Extract the session ID
        logs_expiry = settings.LOGS_EXPIRATION_TIME_IN_SECOND
        session_id: str = UserSessionUtils.get_session_id(request=request)

        serializer = StoreLogMessagesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extract the log message from the validated data
        log: str = serializer.validated_data.get("log")
        log_data = json.loads(log)
        timestamp = datetime.now(timezone.utc).timestamp()

        redis_key = (
            f"{LogService.generate_redis_key(session_id=session_id)}:{timestamp}"
        )

        CacheService.set_key(redis_key, log_data, logs_expiry)

        return Response({"message": "Successfully stored the message in redis"})
