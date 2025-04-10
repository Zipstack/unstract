from rest_framework.exceptions import APIException

from prompt_studio.prompt_profile_manager_v2.constants import ProfileManagerKeys
from prompt_studio.prompt_studio_core_v2.constants import ToolStudioErrors


class PlatformServiceError(APIException):
    status_code = 400
    default_detail = ToolStudioErrors.PLATFORM_ERROR


class ToolNotValid(APIException):
    status_code = 400
    default_detail = "Custom tool is not valid."


class IndexingAPIError(APIException):
    status_code = 500
    default_detail = "Error while indexing file"

    def __init__(self, detail: str | None = None, status_code: int = 500):
        super().__init__(detail)
        self.status_code = status_code


class AnswerFetchError(APIException):
    status_code = 500
    default_detail = "Error occured while fetching response for the prompt"

    def __init__(self, detail: str | None = None, status_code: int = 500):
        super().__init__(detail)
        self.status_code = status_code


class DefaultProfileError(APIException):
    status_code = 500
    default_detail = (
        "Default LLM profile is not configured."
        "Please set an LLM profile as default to continue."
    )


class EnvRequired(APIException):
    status_code = 404
    default_detail = "Environment variable not set"


class OutputSaveError(APIException):
    status_code = 500
    default_detail = "Unable to store the output."


class ToolDeleteError(APIException):
    status_code = 500
    default_detail = "Failed to delete the error"


class NoPromptsFound(APIException):
    status_code = 404
    default_detail = "No prompts available to process"


class PermissionError(APIException):
    status_code = 403
    default_detail = "You do not have permission to perform this action."


class EmptyPromptError(APIException):
    status_code = 422
    default_detail = "Prompt(s) cannot be empty"


class MaxProfilesReachedError(APIException):
    status_code = 403
    default_detail = (
        f"Maximum number of profiles (max {ProfileManagerKeys.MAX_PROFILE_COUNT})"
        " per prompt studio project has been reached."
    )


class OperationNotSupported(APIException):
    status_code = 403
    default_detail = (
        "This feature is not supported "
        "in the open-source version. "
        "Please check our cloud or enterprise on-premise offering  "
        "for access to this functionality."
    )


class PromptNotRun(APIException):
    status_code = 403
    default_detail = (
        "The prompt must be executed before "
        "it can be used as a variable in another prompt. "
        "Please execute the prompt first and try again."
    )

    def __init__(self, detail: str | None = None, code: int | None = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)
