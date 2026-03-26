class RequestKey:
    """Commonly used keys in requests/repsonses."""

    REQUEST = "request"
    PROJECT = "project"
    WORKFLOW = "workflow"
    CREATED_BY = "created_by"
    MODIFIED_BY = "modified_by"
    MODIFIED_AT = "modified_at"


class FieldLengthConstants:
    """Used to determine length of fields in a model."""

    ORG_NAME_SIZE = 64
    CRON_LENGTH = 256
    UUID_LENGTH = 36
    # Not to be confused with a connector instance
    CONNECTOR_ID_LENGTH = 128
    ADAPTER_ID_LENGTH = 128


class RequestMethod:
    """HTTP request method constants."""

    DELETE = "DELETE"
    GET = "GET"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    SAFE_METHODS = frozenset({GET, HEAD, OPTIONS})


class RequestHeader:
    """Request header constants."""

    X_API_KEY = "X-API-KEY"


class UrlPathConstants:
    PROMPT_STUDIO = "prompt-studio/"


class FeatureFlag:
    """Temporary feature flags."""

    APP_DEPLOYMENT = "app_deployment"
