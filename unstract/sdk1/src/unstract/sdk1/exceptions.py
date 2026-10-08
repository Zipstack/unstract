import ast
import json
import logging
import re

import openai

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


# Prefixes litellm stacks ahead of the provider body, in order. Its subclasses
# re-prefix the parent's message ("litellm.ContextWindowExceededError:
# litellm.BadRequestError: ...") and some mappings repeat the class bare
# ("AuthenticationError: MistralException - ...").
_LITELLM_CLASS_PREFIX = re.compile(r"^(?:litellm\.)?(?:\w+Error|Timeout):\s*")
# "AnthropicException - ", "AnthropicError - ", "AzureException NotFoundError - ",
# "BedrockException Invalid Authentication - "
_PROVIDER_TAG_PREFIX = re.compile(r"^\w+(?:Exception|Error)(?:\s+[\w ]+?)?\s+-\s+")
# Calls routed through the OpenAI SDK carry its str(): "Error code: 404 - {...}".
_OPENAI_SDK_PREFIX = re.compile(r"^Error code:\s*\d+\s+-\s+")
_LITELLM_HANDLE_HINT = re.compile(r"\.?\s*Handle with `litellm\.\w+`\.?\s*$")
# The streaming path formats the raw httpx body with str(bytes): b'{...}'.
_BYTES_REPR = re.compile(r"^b(['\"]).*\1$", re.DOTALL)
# Bodies past this size are shown as-is rather than parsed.
_MAX_PARSED_BODY_CHARS = 64_000


def _strip_repeated(pattern: re.Pattern[str], text: str) -> str:
    while True:
        stripped = pattern.sub("", text, count=1)
        if stripped == text:
            return text
        text = stripped


def _unwrap_bytes_repr(body: str) -> str:
    if not _BYTES_REPR.match(body):
        return body
    raw = ast.literal_eval(body)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return body


def _parse_body(body: str) -> object:
    """Parse a provider body given as JSON or as a Python dict repr."""
    if len(body) > _MAX_PARSED_BODY_CHARS or not body.startswith("{"):
        return None
    try:
        return json.loads(body)
    except ValueError:
        pass
    try:
        return ast.literal_eval(body)
    except (ValueError, SyntaxError):
        return None


def _extract_provider_message(body: str) -> tuple[str, str | None]:
    """Pull the human message and request id out of a provider's error body.

    Falls back to the body as-is when it cannot be parsed or has no known
    message field.
    """
    payload = _parse_body(body)
    if not isinstance(payload, dict):
        return body, None

    error = payload.get("error")
    error_dict = error if isinstance(error, dict) else {}
    message = (
        error_dict.get("message")
        or (error if isinstance(error, str) else None)
        or payload.get("message")
        or payload.get("detail")
    )
    request_id = payload.get("request_id") or error_dict.get("request_id")
    if not isinstance(request_id, str):
        request_id = None
    if not isinstance(message, str) or not message:
        return body, request_id
    return message, request_id


def format_provider_error(e: Exception) -> str:
    """Render a litellm provider error as one readable line.

    Keeps the error class and HTTP status that litellm's string form either
    hides or buries, and points at the adapter's model when the provider
    reports it as not found — Anthropic's 404 for a retired model says only
    ``model: <id>``. Never raises: it runs inside error handlers, so anything
    unparseable falls back to the litellm text.
    """
    cleaned = strip_litellm_prefix(str(e))
    if not isinstance(e, openai.APIError):
        return cleaned
    try:
        return _render_provider_error(e, cleaned)
    except Exception:
        logger.warning("Could not format provider error", exc_info=True)
        return cleaned


def _render_provider_error(e: openai.APIError, cleaned: str) -> str:
    body = _strip_repeated(_LITELLM_CLASS_PREFIX, cleaned)
    body = _PROVIDER_TAG_PREFIX.sub("", body, count=1)
    body = _OPENAI_SDK_PREFIX.sub("", body, count=1)
    body = _LITELLM_HANDLE_HINT.sub("", body)
    message, request_id = _extract_provider_message(_unwrap_bytes_repr(body))

    label = type(e).__name__
    # litellm assigns a status to failures that never got a response (a
    # refused connection is an InternalServerError with 500); it records the
    # response headers only when one actually came back.
    status_code = getattr(e, "status_code", None)
    if status_code and getattr(e, "litellm_response_headers", None) is not None:
        label += f" (HTTP {status_code})"
    text = f"{label}: {message}"
    if request_id:
        text += f" (request_id: {request_id})"

    model = getattr(e, "model", None)
    if isinstance(e, openai.NotFoundError) and model:
        text = text.rstrip(". ")
        text += (
            f". Model '{model}' was not found by the provider; it may have "
            "been retired, or the model name or endpoint may be incorrect. "
            "Update the model configured in this adapter."
        )
    return text


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

    cleaned_message = format_provider_error(e)
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
