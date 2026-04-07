"""Standalone exceptions for the legacy executor.

Adapted from prompt-service exceptions. The Flask ``APIError`` base
class is replaced with ``LegacyExecutorError`` so these exceptions
work outside of Flask (i.e. inside the Celery executor worker).
"""


class LegacyExecutorError(Exception):
    """Base exception for legacy executor errors.

    Replaces Flask's ``APIError`` — carries ``message`` and ``code``
    attributes so callers can map to ``ExecutionResult.failure()``.
    """

    code: int = 500
    message: str = "Internal executor error"

    def __init__(self, message: str | None = None, code: int | None = None):
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        super().__init__(self.message)


class BadRequest(LegacyExecutorError):
    code = 400
    message = "Bad Request / No payload"


class RateLimitError(LegacyExecutorError):
    code = 429
    message = "Running into rate limit errors, please try again later"


class MissingFieldError(LegacyExecutorError):
    """Custom error for missing fields."""

    def __init__(self, missing_fields: list[str]):
        message = f"Missing required fields: {', '.join(missing_fields)}"
        super().__init__(message=message)


class RetrievalError(LegacyExecutorError):
    """Custom exception raised for errors during retrieval from VectorDB."""

    DEFAULT_MESSAGE = (
        "Error while retrieving data from the VectorDB. "
        "Please contact the admin for further assistance."
    )


class ExtractionError(LegacyExecutorError):
    DEFAULT_MESSAGE = "Error while extracting from a document"


class UnprocessableEntity(LegacyExecutorError):
    code = 422
    message = "Unprocessable Entity"


class CustomDataError(LegacyExecutorError):
    """Custom exception raised for errors with custom_data variables."""

    code = 400

    def __init__(self, variable: str, reason: str, is_ide: bool = True):
        if is_ide:
            help_text = "Please define this key in Prompt Studio Settings > Custom Data."
        else:
            help_text = (
                "Please include this key in the 'custom_data' field of your API request."
            )
        variable_display = "{{custom_data." + variable + "}}"
        message = (
            f"Custom data error for variable '{variable_display}': {reason} {help_text}"
        )
        super().__init__(message=message)
