from rest_framework.exceptions import APIException


class ProviderNotFound(APIException):
    status_code = 404
    default_detail = "The requested provider was not found."
