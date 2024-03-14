from rest_framework.exceptions import APIException


class UserIdNotExist(APIException):
    status_code = 404
    default_detail = "User ID does not exist"


class UserAlreadyExistInOrganization(APIException):
    status_code = 403
    default_detail = "User allready exist in the organization"


class OrganizationNotExist(APIException):
    status_code = 404
    default_detail = "Organization does not exist"


class UnknownException(APIException):
    status_code = 500
    default_detail = "An unexpected error occurred"


class BadRequestException(APIException):
    status_code = 400
    default_detail = "Bad Request"


class InactiveOrganization(APIException):
    status_code = 400
    default_detail = (
        "Selected organization is not active. Please contact admin."
    )
    default_code = "subscription_error"


class TrialExpired(APIException):
    status_code = 402
    default_detail = "Trial period expired. Please contact sales/admin."
    default_code = "subscription_error"
