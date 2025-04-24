import logging
from typing import Any

from account_v2.models import User
from connector_auth_v2.constants import ConnectorAuthKey, SocialAuthConstants
from connector_auth_v2.models import ConnectorAuth
from connector_auth_v2.pipeline.google import GoogleAuthHelper
from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import PermissionDenied
from social_core.backends.oauth import BaseOAuth2

logger = logging.getLogger(__name__)


def check_user_exists(backend: BaseOAuth2, user: User, **kwargs: Any) -> dict[str, str]:
    """Checks if user is authenticated (will be handled in auth middleware,
    present as a fail safe)

    Args:
        user (account.User): User model

    Raises:
        PermissionDenied: Unauthorized user

    Returns:
        dict: Carrying response details for auth pipeline
    """
    if not user:
        raise PermissionDenied(backend)
    return {**kwargs}


def cache_oauth_creds(
    backend: BaseOAuth2,
    details: dict[str, str],
    response: dict[str, str],
    uid: str,
    user: User,
    *args: Any,
    **kwargs: Any,
) -> dict[str, str]:
    """Used to cache the extra data JSON in redis against a key.

    This contains the access and refresh token along with details
    regarding expiry, uid (unique ID given by provider) and provider.
    """
    cache_key = kwargs.get("cache_key") or backend.strategy.session_get(
        settings.SOCIAL_AUTH_FIELDS_STORED_IN_SESSION[0],
        ConnectorAuthKey.OAUTH_KEY,
    )
    extra_data = backend.extra_data(user, uid, response, details, *args, **kwargs)
    extra_data[SocialAuthConstants.PROVIDER] = backend.name
    extra_data[SocialAuthConstants.UID] = uid

    if backend.name == SocialAuthConstants.GOOGLE_OAUTH:
        extra_data = GoogleAuthHelper.enrich_connector_metadata(extra_data)

    cache.set(
        cache_key,
        extra_data,
        int(settings.SOCIAL_AUTH_EXTRA_DATA_EXPIRATION_TIME_IN_SECOND),
    )
    return {**kwargs}


class ConnectorAuthHelper:
    @staticmethod
    def get_oauth_creds_from_cache(
        cache_key: str, delete_key: bool = True
    ) -> dict[str, str] | None:
        """Retrieves oauth credentials from the cache.

        Args:
            cache_key (str): Key to obtain credentials from

        Returns:
            Optional[dict[str,str]]: Returns credentials. None if it doesn't exist
        """
        oauth_creds: dict[str, str] = cache.get(cache_key)
        if delete_key:
            cache.delete(cache_key)
        return oauth_creds

    @staticmethod
    def get_or_create_connector_auth(
        oauth_credentials: dict[str, str],
        user: User = None,  # type: ignore
    ) -> ConnectorAuth:
        """Gets or creates a ConnectorAuth object.

        Args:
            user (User): Used while creation, can be removed if not required
            oauth_credentials (dict[str,str]): Needs to have provider and uid

        Returns:
            ConnectorAuth: Object for the respective provider/uid
        """
        ConnectorAuth.check_credential_format(oauth_credentials)
        provider = oauth_credentials[SocialAuthConstants.PROVIDER]
        uid = oauth_credentials[SocialAuthConstants.UID]
        connector_oauth: ConnectorAuth = ConnectorAuth.get_social_auth(
            provider=provider, uid=uid
        )
        if not connector_oauth:
            connector_oauth = ConnectorAuth.create_social_auth(
                user, uid=uid, provider=provider
            )

        # TODO: Remove User's related manager access to ConnectorAuth
        connector_oauth.set_extra_data(oauth_credentials)  # type: ignore
        return connector_oauth
