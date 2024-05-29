import json
import logging
import os
from datetime import datetime, timezone

import redis
from logs_helper.constants import LogsHelperKeys
from logs_helper.exceptions import InvalidValueError, MissingFieldsKeyError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from utils.local_context import StateStore

from .serializers import StoreLogMessagesSerializer

logger = logging.getLogger(__name__)


class LogsHelperView(viewsets.ModelViewSet):
    """Viewset to handle all Tool Studio prompt related API logics."""

    r = redis.Redis(
        host=os.environ.get("REDIS_HOST", "http://localhost"),
        port=os.environ.get("REDIS_PORT", "6379"),
        username=os.environ.get("REDIS_USER", ""),
        password=os.environ.get("REDIS_PASSWORD", ""),
    )

    @action(detail=False, methods=["get"])
    def get_logs(self, request):
        try:
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
        except Exception as e:
            # Handle other exceptions
            error_msg = "An unexpected error occurred while retrieving logs"
            logger.error(f"{error_msg}: {e}")
            raise APIException(error_msg)

    @action(detail=False, methods=["post"])
    def store_log(self, request):
        """Store log message in Redis."""
        try:
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
        except KeyError as e:
            # Handle KeyError
            logger.error(f"Log is missing: {e}")
            raise MissingFieldsKeyError()
        except ValueError as e:
            # Handle ValueError
            logger.error(f"Invalid value: {e}")
            raise InvalidValueError()
        except Exception as e:
            # Handle other exceptions
            error_msg = "An unexpected error occurred while store the log message"
            logger.error(f"{error_msg}: {e}")
            raise APIException(error_msg)
