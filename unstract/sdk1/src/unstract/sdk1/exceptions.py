import logging
import re

import openai
from litellm import exceptions as litellm_exceptions

logger = logging.getLogger(__name__)


class SdkError(Exception):
    DEFAULT_MESSAGE = "Something went wrong"
    actual_err: Exception | None = None
    status_code: int | None = None

    def __init__(
        self,
        message: str = DEFAULT_MESSAGE,
        status_code: int | None = None,
        actual_err: Exception | None = None,
    ) -> None:
        """Initialize the SdkError exception.

        Args:
            message: Error message description
            status_code: HTTP status code associated with the error
            actual_err: The original exception that caused this error
        """
        super().__init__(message)
        # Make it user friendly wherever possible
        self.message = message
        if actual_err:
            self.actual_err = actual_err

        # Setting status code for error
        if status_code:
            self.status_code = status_code
        elif actual_err:
            if hasattr(actual_err, "status_code"):  # Most providers
                self.status_code = actual_err.status_code
            elif hasattr(actual_err, "http_status"):  # Few providers like Mistral
                self.status_code = actual_err.http_status
            elif hasattr(actual_err, "response") and hasattr(
                actual_err.response, "status_code"
            ):  # requests.HTTPError
                self.status_code = actual_err.response.status_code

    def __str__(self) -> str:
        """Return string representation of the SdkError."""
        return self.message


class IndexingError(SdkError):
    def __init__(self, message: str = "", **kwargs: object) -> None:
        """Initialize the IndexingError exception.

        Args:
            message: Error message description
            **kwargs: Additional keyword arguments passed to parent SdkError
        """
        if "404" in message:
            message = "Index not found. Please check vector DB settings."
        super().__init__(message, **kwargs)


class LLMError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to LLM"


class EmbeddingError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to embedding"


class VectorDBError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to vector DB"


class X2TextError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to text extractor"


class OCRError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to OCR"


class RateLimitError(SdkError):
    DEFAULT_MESSAGE = "Running into rate limit errors, please try again later"


class ContextWindowExceededError(SdkError):
    """The prompt (plus context) exceeded the model's context window.

    UN-3133: litellm raises ``ContextWindowExceededError``, which derives from
    ``BadRequestError`` and so from ``openai.APIError``. Without a distinct
    class it was wrapped as a plain ``SdkError`` carrying the provider's raw
    400 text, so the UI showed a generic "Error from <provider>" and the real
    cause was only findable by reading worker logs.
    """

    DEFAULT_MESSAGE = (
        "The document and prompt together exceed the model's context window. "
        "Reduce the chunk size, limit the pages extracted, or use a model with "
        "a larger context window."
    )


class FileStorageError(SdkError):
    DEFAULT_MESSAGE = (
        "Error while connecting with the storage. "
        "Please check the configuration credentials"
    )


class FileOperationError(SdkError):
    DEFAULT_MESSAGE = (
        "Error while performing operation on the file. "
        "Please check specific storage error for "
        "further information"
    )


def strip_litellm_prefix(error_message: str) -> str:
    """Remove litellm implementation details from error messages.

    Strips internal litellm prefixes and retry information to show
    only the actual provider error to users.

    Handles patterns:
    - "litellm.RateLimitError: message" → "message"
    - "litellm.AuthenticationError: message" → "message"
    - "litellm.Timeout: message" → "message"
    - "message LiteLLM Retried: 3 times" → "message"
    - "message, LiteLLM Max Retries: 5" → "message"

    Args:
        error_message: Raw error message from litellm

    Returns:
        Clean error message without litellm prefix/suffix
    """
    logger.info(f"Stripping litellm prefix from error: {error_message}")

    # Strip "litellm.XxxError: " or "litellm.Xxx: "
    # prefix (handles both error classes and non-error classes like Timeout)
    cleaned = re.sub(r"^litellm\.\w+:\s*", "", error_message, flags=re.IGNORECASE)

    # Strip retry information suffix
    cleaned = re.sub(r"\s*LiteLLM\s+(Retried|Max\s+Retries):[^,]*,?\s*", "", cleaned)

    return cleaned.strip()


def parse_litellm_err(e: Exception, provider_name: str | None = None) -> SdkError:
    """Parse litellm errors - both LLM and embedding provider's.

    Wraps provider exceptions with user-friendly messages
    indicating error is from 3rd party service.

    Args:
        e: Exception from litellm
        provider_name: Name of the provider

    Returns:
        SdkError: Wrapped error with clear message
    """
    # litellm derives from OpenAI's error class, avoid parsing other errors
    if not isinstance(e, openai.APIError):
        return e

    # Extract status code robustly from provider exceptions
    status_code = (
        getattr(e, "status_code", None)
        or getattr(e, "http_status", None)
        or getattr(e, "code", None)
    )

    cleaned_message = strip_litellm_prefix(str(e))

    # UN-3133: surface a context-window overflow as its own error type with an
    # actionable message. It is a BadRequestError subclass, so without this it
    # collapses into the generic wrap below and the user sees only the
    # provider's raw 400.
    if isinstance(e, litellm_exceptions.ContextWindowExceededError):
        err = ContextWindowExceededError(
            ContextWindowExceededError.DEFAULT_MESSAGE,
            actual_err=e,
            status_code=status_code,
        )
        # Return early: the generic tail below would overwrite the actionable
        # guidance with "Error from <provider>." and leave only the raw 400.
        # The provider text is kept underneath it for support/debugging.
        err.message = (
            f"{ContextWindowExceededError.DEFAULT_MESSAGE}"
            f"\n```\n{cleaned_message}\n```"
        )
        return err

    err = SdkError(cleaned_message, actual_err=e, status_code=status_code)

    if not provider_name:
        provider_name = getattr(e, "llm_provider", "")  # litellm handles it this way
    msg = f"Error from {provider_name}."

    # Add code block for errors from clients
    if err.actual_err:
        msg += f"\n```\n{cleaned_message}\n```"
    else:
        msg += cleaned_message

    err.message = msg
    return err
