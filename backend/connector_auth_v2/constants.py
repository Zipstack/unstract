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
