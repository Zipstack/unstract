from rest_framework.exceptions import APIException


class JobSchedulingError(APIException):
    status_code = 500
    default_detail = "Error occured while scheduling the job"


class JobDeletionError(APIException):
    status_code = 404
    default_detail = "Error occured while deleting the job"
