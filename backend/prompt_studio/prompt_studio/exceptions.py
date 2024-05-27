from rest_framework.exceptions import APIException


class IndexingError(APIException):
    status_code = 400
    default_detail = "Error while indexing file"


class AnswerFetchError(APIException):
    status_code = 400
    default_detail = "Error occured while fetching response for the prompt"


class ToolNotValid(APIException):
    status_code = 400
    default_detail = "Custom tool is not valid."
