"""Provider failure details (provider, request id, retry hint) from an error chain.

sdk1 wraps a litellm / OpenAI SDK error in ``SdkError`` (``actual_err``, and
``raise ... from``), and the executor wraps that in ``LegacyExecutorError``.
This walks the chain to the provider error and reads only these three values.
Headers, bodies and messages are never copied, so no credential can leak.
"""

import logging
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import openai

logger = logging.getLogger(__name__)

_REQUEST_ID_HEADERS = (
    "x-request-id",
    "request-id",
    "apim-request-id",
    "x-amzn-requestid",
    "x-ms-request-id",
)
_MAX_TEXT_CHARS = 128
_MAX_CHAIN_DEPTH = 10


def provider_error_details(exc: BaseException) -> dict[str, Any] | None:
    """Return ``{provider, request_id, retry_after_seconds}`` or ``None``.

    ``None`` when the chain holds no provider error or it carries none of the
    three values. Never raises: it runs inside error handlers.
    """
    try:
        provider_exc = _find_provider_error(exc)
        if provider_exc is None:
            return None
        headers = _headers(provider_exc)
        details = {
            "provider": _text(getattr(provider_exc, "llm_provider", None)),
            "request_id": _text(getattr(provider_exc, "request_id", None))
            or _request_id_from(headers),
            "retry_after_seconds": _retry_after(headers),
        }
    except Exception:
        logger.debug("Could not read provider error details", exc_info=True)
        return None
    if all(value is None for value in details.values()):
        return None
    return details


def _find_provider_error(exc: BaseException) -> openai.APIError | None:
    current: Any = exc
    for _ in range(_MAX_CHAIN_DEPTH):
        if current is None:
            return None
        if isinstance(current, openai.APIError):
            return current
        current = (
            getattr(current, "actual_err", None)
            or current.__cause__
            or current.__context__
        )
    return None


def _headers(exc: openai.APIError) -> dict[str, str]:
    """Lower-cased headers from litellm's copy and from the HTTP response."""
    merged: dict[str, str] = {}
    response = getattr(exc, "response", None)
    for source in (
        getattr(response, "headers", None),
        getattr(exc, "litellm_response_headers", None),
    ):
        if source is None:
            continue
        for key, value in source.items():
            merged[str(key).lower()] = str(value)
    return merged


def _request_id_from(headers: dict[str, str]) -> str | None:
    for name in _REQUEST_ID_HEADERS:
        value = _text(headers.get(name))
        if value:
            return value
    return None


def _retry_after(headers: dict[str, str]) -> int | None:
    millis = _number(headers.get("retry-after-ms"))
    if millis is not None:
        return math.ceil(millis / 1000)
    raw = headers.get("retry-after")
    seconds = _number(raw)
    if seconds is not None:
        return math.ceil(seconds)
    return _seconds_until(raw)


def _number(raw: str | None) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _seconds_until(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0, math.ceil((when - datetime.now(UTC)).total_seconds()))


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:_MAX_TEXT_CHARS] or None
