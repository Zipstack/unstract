from rest_framework.exceptions import APIException


class InternalError(APIException):
    status_code = 500
    default_detail = "Internal service error."


class ToolDoesNotExist(APIException):
    status_code = 500
    default_detail = "Tool does not exist."


class ToolSaveError(APIException):
    status_code = 500
    default_detail = "Error while saving the tool."


class MandatoryFieldMissingError(APIException):
    status_code = 400
    default_detail = "Mandatory field missing."


class ProfileErrors(APIException):
    status_code = 400
    default_detail = f"""Looks like some default values are 
        not selected. Please check profile managers."""


class DuplicateData(APIException):
    status_code = 400
    default_detail = "Duplicate Data"
