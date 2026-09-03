"""Standalone exceptions for the legacy executor.

Adapted from prompt-service exceptions. The Flask ``APIError`` base
class is replaced with ``LegacyExecutorError`` so these exceptions
work outside of Flask (i.e. inside the Celery executor worker).
"""

from unstract.core.prompt_run_cancellation import PROMPT_RUN_CANCELLED_ERROR


class LegacyExecutorError(Exception):
    """Base exception for legacy executor errors.

    ``partial_usage_records`` preserves billing rows across mid-pipeline failures.
    """

    code: int = 500
    message: str = "Internal executor error"

    def __init__(
        self,
        message: str | None = None,
        code: int | None = None,
        partial_usage_records: list[dict] | None = None,
    ):
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        self.partial_usage_records: list[dict] = list(partial_usage_records or [])
        super().__init__(self.message)


class ExecutionCancelled(LegacyExecutorError):
    """The user stopped this run from Prompt Studio (UN-1031).

    A ``LegacyExecutorError`` so it inherits ``partial_usage_records`` — tokens
    already spent before the stop are still billed — and so ``execute()``'s
    existing handler turns it into a result rather than letting it escape into
    the consumer's retry path. The message is the shared sentinel every layer
    matches on, so callers can tell a stop apart from a genuine failure.
    """

    code = 499  # nginx's "client closed request"; never rendered to a user
    message = PROMPT_RUN_CANCELLED_ERROR


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
