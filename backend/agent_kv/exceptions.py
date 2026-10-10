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
