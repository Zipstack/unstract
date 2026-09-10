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
        if key_obj.organization_id is None:
            # `organization` is nullable on the model (DefaultOrganizationMixin
            # fills it from UserContext at save time), but EVERY downstream use
            # of a key is org-scoped: the subscription gate, the concurrency
            # limiter, the storage prefix and every job lookup. A key with no
            # organization cannot scope any of them, so it is not a usable key.
            # Refused once here, at the auth boundary, rather than surfacing as
            # a null dereference inside whichever view happens to touch the
            # organization first.
            logger.error(
                "agent-kv key %s has no organization; refusing the request",
                key_obj.id,
            )
            raise Forbidden("Invalid api key")
        kwargs["agent_kv_key"] = key_obj
        return func(self, request, *args, **kwargs)
