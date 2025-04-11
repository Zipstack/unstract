from rest_framework.exceptions import APIException


class CacheMissException(APIException):
    status_code = 404
    default_detail = "Key doesn't exist."


class EnrichConnectorMetadataException(APIException):
    status_code = 500
    default_detail = "Connector metadata could not be enriched"


class MissingParamException(APIException):
    status_code = 400
    default_detail = "Bad request, missing parameter."

    def __init__(
        self,
        code: str | None = None,
        param: str | None = None,
    ) -> None:
        detail = f"Bad request, missing parameter: {param}"
        super().__init__(detail, code)


class KeyNotConfigured(APIException):
    status_code = 500
    default_detail = "Key is not configured correctly"
