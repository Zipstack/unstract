from rest_framework.exceptions import APIException


class EngineUnavailable(APIException):
    status_code = 501
    default_detail = "agent-kv engine not available on this deployment"


class RateLimited(APIException):
    status_code = 429
    default_detail = "Too many requests"


class JobNotFound(APIException):
    status_code = 404
    default_detail = "Job not found"


class SubscriptionGateUnavailable(APIException):
    """The engine plugin is installed but exposes no subscription gate.

    Deliberately NOT a 402: the org's subscription was never evaluated, so
    claiming it was denied would be a lie. This is a deployment fault — a build
    that can run billable work but cannot check entitlement — and it fails
    CLOSED, because the alternative is admitting unmetered paid work on a route
    whose URL carries no org segment for the middleware to fall back on.
    """

    status_code = 503
    default_detail = (
        "agent-kv cannot verify subscription entitlement on this deployment; "
        "the engine plugin exposes no subscription gate"
    )
