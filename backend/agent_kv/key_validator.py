import logging
import uuid

from api_v2.api_key_validator import BaseAPIKeyValidator
from api_v2.exceptions import Forbidden

from agent_kv.models import AgentKVKey

logger = logging.getLogger(__name__)

# One message for every rejection reason, deliberately. A caller holding a bad
# key learns only that it is bad -- not whether it was malformed, unknown,
# inactive, or missing an organization -- so the response cannot be used to
# probe which keys exist. Named once so the three raise sites cannot drift
# apart and start leaking that distinction.
_INVALID_KEY = "Invalid api key"


class AgentKVKeyValidator(BaseAPIKeyValidator):
    @staticmethod
    def validate_and_process(self, request, func, api_key, *args, **kwargs):
        try:
            uuid.UUID(api_key)
        except (ValueError, AttributeError):
            raise Forbidden(_INVALID_KEY)
        try:
            key_obj = AgentKVKey.objects.get(key=api_key, is_active=True)
        except AgentKVKey.DoesNotExist:
            raise Forbidden(_INVALID_KEY)
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
            raise Forbidden(_INVALID_KEY)
        kwargs["agent_kv_key"] = key_obj
        return func(self, request, *args, **kwargs)
