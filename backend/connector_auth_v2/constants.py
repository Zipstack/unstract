class ConnectorAuthKey:
    OAUTH_KEY = "oauth-key"


class SocialAuthConstants:
    UID = "uid"
    PROVIDER = "provider"
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    TOKEN_TYPE = "token_type"
    AUTH_TIME = "auth_time"
    EXPIRES = "expires"

    REFRESH_AFTER_FORMAT = "%d/%m/%Y %H:%M:%S"
    REFRESH_AFTER = "refresh_after"  # Timestamp to refresh tokens after

    GOOGLE_OAUTH = "google-oauth2"
    GOOGLE_TOKEN_EXPIRY_FORMAT = "%d/%m/%Y %H:%M:%S"


# OAuth token-specific keys safe to merge across connectors sharing the same
# (provider, uid). Anything outside this set (form fields like site_url,
# drive_id, or provider-specific enrichment stored in ConnectorAuth.extra_data)
# must NOT leak between connectors.
OAUTH_TOKEN_KEYS: frozenset[str] = frozenset(
    {
        SocialAuthConstants.ACCESS_TOKEN,
        SocialAuthConstants.REFRESH_TOKEN,
        SocialAuthConstants.TOKEN_TYPE,
        SocialAuthConstants.EXPIRES,
        SocialAuthConstants.AUTH_TIME,
        SocialAuthConstants.REFRESH_AFTER,
        "expires_in",
        "scope",
    }
)
