"""Egress checks for the tenant-supplied Unstructured API URL.

The ``unstructured-url`` form field comes from an adapter any org user can
configure, and this service POSTs the uploaded document to it. The shared guard
in ``unstract.core.network.ssrf`` decides whether that URL may be dialled.

Whether a private, loopback or link-local destination is allowed depends on the
deployment. Self-hosted (OSS and on-prem) installs routinely run Unstructured on
localhost or a private host, so it is allowed by default. A multi-tenant cloud
deployment must refuse it, and does so by setting
``UNSTRUCTURED_URL_ALLOW_PRIVATE=false``.
"""

import logging
import os

from unstract.core.network.ssrf import (
    REFUSED_INTERNAL_LITERAL,
    REFUSED_NON_PUBLIC,
    UNRESOLVABLE,
    safe_host,
    webhook_url_refusal,
)

logger = logging.getLogger(__name__)

ALLOW_PRIVATE_ENV = "UNSTRUCTURED_URL_ALLOW_PRIVATE"
REQUEST_TIMEOUT_ENV = "UNSTRUCTURED_REQUEST_TIMEOUT"

# Connecting is quick or it is not going to work; reading is where a large
# document spends its time.
CONNECT_TIMEOUT = 10.0
# Just under the gunicorn worker timeout (300s in x2text.Dockerfile), so a slow
# Unstructured call ends in an error response rather than a killed worker.
DEFAULT_READ_TIMEOUT = 290.0

_TRUE_VALUES = ("1", "true", "yes")


def allow_private() -> bool:
    """Whether private, loopback and link-local destinations are allowed.

    Defaults to allowed, so a self-hosted install keeps working unchanged. Any
    value other than a recognised true value refuses them.
    """
    return os.environ.get(ALLOW_PRIVATE_ENV, "true").strip().lower() in _TRUE_VALUES


def request_timeout() -> tuple[float, float]:
    """The ``(connect, read)`` timeout for calls to the Unstructured API."""
    raw = os.environ.get(REQUEST_TIMEOUT_ENV, "")
    try:
        read = float(raw) if raw.strip() else DEFAULT_READ_TIMEOUT
    except ValueError:
        logger.warning(
            "Ignoring invalid %s=%r; using %ss",
            REQUEST_TIMEOUT_ENV,
            raw,
            DEFAULT_READ_TIMEOUT,
        )
        read = DEFAULT_READ_TIMEOUT
    if read <= 0:
        read = DEFAULT_READ_TIMEOUT
    return CONNECT_TIMEOUT, read


def refusal_message(url: str) -> str | None:
    """A message for the caller if ``url`` may not be dialled, else None.

    The scheme, credential and parser-agreement checks always apply. The
    destination check applies only when private destinations are not allowed;
    when they are, no lookup is made here and the URL is dialled as before.
    """
    if allow_private():
        reason = webhook_url_refusal(url, resolve=False)
        # resolve=False reports an internal literal (or localhost) as its last
        # check, after every syntactic one, so waiving it waives nothing else.
        if reason == REFUSED_INTERNAL_LITERAL:
            reason = None
    else:
        reason = webhook_url_refusal(url)

    if reason is None:
        return None

    # The host only: the URL can carry a key in its query string.
    logger.warning(
        "Refusing unstructured-url: %s (host=%s, %s=%s)",
        reason,
        safe_host(url),
        ALLOW_PRIVATE_ENV,
        allow_private(),
    )
    if reason == UNRESOLVABLE:
        return "Unstructured URL host could not be resolved"
    if reason in (REFUSED_INTERNAL_LITERAL, REFUSED_NON_PUBLIC):
        return (
            "Unstructured URL points to a private, loopback or link-local "
            "address, which is not allowed on this deployment"
        )
    return f"Unstructured URL is not allowed ({reason})"
