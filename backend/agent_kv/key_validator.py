import logging
import uuid

from api_v2.api_key_validator import BaseAPIKeyValidator
from api_v2.exceptions import Forbidden

from agent_kv.models import AgentKVKey

logger = logging.getLogger(__name__)


class AgentKVKeyValidator(BaseAPIKeyValidator):
    @staticmethod
    def validate_and_process(self, request, func, api_key, *args, **kwargs):
        try:
            uuid.UUID(api_key)
        except (ValueError, AttributeError):
            raise Forbidden("Invalid api key")
        try:
            key_obj = AgentKVKey.objects.get(key=api_key, is_active=True)
        except AgentKVKey.DoesNotExist:
            raise Forbidden("Invalid api key")
        kwargs["agent_kv_key"] = key_obj
        return func(self, request, *args, **kwargs)
