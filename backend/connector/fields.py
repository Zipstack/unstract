from datetime import datetime

from connector_auth.constants import SocialAuthConstants
from connector_auth.models import ConnectorAuth
from django.db import models
import logging

logger = logging.getLogger(__name__)


class ConnectorAuthJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):  # type: ignore
        """ Overrding default function. """
        metadata = super().from_db_value(value, expression, connection)
        provider = metadata.get(SocialAuthConstants.PROVIDER)
        uid = metadata.get(SocialAuthConstants.UID)
        if provider and uid:
            refresh_after_str = metadata.get(SocialAuthConstants.REFRESH_AFTER)
            if refresh_after_str:
                refresh_after = datetime.strptime(
                    refresh_after_str, SocialAuthConstants.REFRESH_AFTER_FORMAT
                )
                if datetime.now() > refresh_after:
                    metadata = self._refresh_tokens(provider, uid)
        return metadata

    def _refresh_tokens(self, provider: str, uid: str) -> dict[str, str]:
        """Retrieves PSA object and refreshes the token if necessary."""
        connector_auth: ConnectorAuth = ConnectorAuth.get_social_auth(
            provider=provider, uid=uid
        )
        tokens_refreshed = False
        if connector_auth:
            (
                connector_metadata,
                tokens_refreshed,
            ) = connector_auth.get_and_refresh_tokens()
        return connector_metadata  # type: ignore
