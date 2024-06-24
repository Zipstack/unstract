from rest_framework.exceptions import APIException


class BadRequestException(APIException):
    status_code = 400
    default_detail = "Bad Request."


class ShareControllerException(Exception):
    def __init__(self, message: str = "Something went wrong"):
        super().__init__(message)
        # Make it user friendly wherever possible
        self.message = message

    def __str__(self) -> str:
        return self.message
