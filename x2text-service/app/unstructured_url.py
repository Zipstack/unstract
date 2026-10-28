"""Egress checks for the tenant-supplied Unstructured API URL.

The ``unstructured-url`` form field comes from an adapter any org user can
configure, and this service POSTs the uploaded document to it. The shared guard
in ``unstract.core.network.ssrf`` decides whether that URL may be dialled.

Whether a private, loopback or link-local destination is allowed depends on the
deployment. docker-compose (OSS) installs routinely run Unstructured on
localhost or a private host, so it is allowed when the setting is unset. A
deployment serving untrusted tenants must refuse it by setting
``UNSTRUCTURED_URL_ALLOW_PRIVATE=false``.

Redirects follow the same rule. Where private destinations are allowed they
are followed as ``requests`` always did. Where they are refused, each hop is
checked with the same guard before it is dialled, up to ``MAX_REDIRECTS``.

With private destinations refused, the name is resolved here and again by
``requests``, so a name re-resolved to an internal address in between is not
caught. The control for that is an egress policy on the pods (see ``ssrf.py``).
"""

import logging
import math
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

import requests

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
# How long to wait for Unstructured to send data. It bounds each wait on the
# socket, not the whole call; Unstructured sends nothing until it has processed
# the document, so in practice it caps processing time. Matches the extraction
# wait default for LLMWhisperer (ADAPTER_LLMW_WAIT_TIMEOUT, 900s).
#
# It only takes effect while gunicorn lets the request run. The sync worker in
# x2text.Dockerfile's CMD is killed once busy past --timeout (930s), so that
# must stay above this. The Helm chart's gthread workers keep heartbeating
# during a request, so its --timeout does not end long calls.
DEFAULT_READ_TIMEOUT = 900.0
# A sanity bound: a day is far beyond any real extraction. (Far larger values,
# around 1e10, overflow CPython's socket timeout.)
MAX_READ_TIMEOUT = 86400.0

_TRUE_VALUES = ("1", "true", "yes")

MAX_REDIRECTS = 5
API_KEY_HEADER = "unstructured-api-key"


# Only its should_strip_auth is used; it holds no connections.
_STRIP_AUTH = requests.Session()


class RedirectRefused(Exception):
    """A redirect from the Unstructured API that will not be followed."""


def allow_private() -> bool:
    """Whether private, loopback and link-local destinations are allowed.

    Unset or empty means allowed. Any other value that is not a recognised true
    value refuses them.
    """
    raw = os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower()
    return not raw or raw in _TRUE_VALUES


def request_timeout() -> tuple[float, float]:
    """The ``(connect, read)`` timeout for calls to the Unstructured API."""
    raw = os.environ.get(REQUEST_TIMEOUT_ENV, "").strip()
    if not raw:
        return CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT
    try:
        read = float(raw)
    except ValueError:
        read = math.nan
    if read > MAX_READ_TIMEOUT:
        logger.warning("Capping %s=%r at %ss", REQUEST_TIMEOUT_ENV, raw, MAX_READ_TIMEOUT)
        return CONNECT_TIMEOUT, MAX_READ_TIMEOUT
    # nan parses, but the socket layer rejects it on every call. (inf is
    # capped above.)
    if not math.isfinite(read) or read <= 0:
        logger.warning(
            "Ignoring invalid %s=%r; using %ss",
            REQUEST_TIMEOUT_ENV,
            raw,
            DEFAULT_READ_TIMEOUT,
        )
        read = DEFAULT_READ_TIMEOUT
    return CONNECT_TIMEOUT, read


def refusal_message(url: str) -> str | None:
    """A message for the caller if ``url`` may not be dialled, else None.

    The scheme, credential and parser-agreement checks always apply. The
    destination check applies only when private destinations are not allowed;
    when they are, no lookup is made here.
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


def post(
    url: str,
    *,
    headers: dict[str, Any],
    data: Any,
    files: Callable[[], Any],
) -> requests.Response:
    """POST to the Unstructured API at ``url``, which the caller has checked.

    ``files`` builds the multipart files afresh, because a 307/308 replays the
    body and a file stream is consumed by each send.

    Raises:
        RedirectRefused: private destinations are refused and a hop is not
            allowed, or there are more than ``MAX_REDIRECTS`` of them.
        requests.RequestException: as ``requests`` raises it.
    """
    timeout = request_timeout()
    if allow_private():
        # Unchanged from before the guard: requests follows redirects itself.
        return requests.request(
            "POST", url, headers=headers, data=data, files=files(), timeout=timeout
        )

    method, body, upload = "POST", data, files()
    for _ in range(MAX_REDIRECTS + 1):
        response = requests.request(
            method,
            url,
            headers=headers,
            data=body,
            files=upload,
            timeout=timeout,
            allow_redirects=False,
        )
        if not response.is_redirect:
            return response
        response.close()
        try:
            next_url = urljoin(url, response.headers["Location"])
        except ValueError:
            raise RedirectRefused(
                "Redirect refused: the Unstructured API sent an unparseable Location"
            ) from None
        if refusal := refusal_message(next_url):
            raise RedirectRefused(f"Redirect refused: {refusal}")
        if _STRIP_AUTH.should_strip_auth(url, next_url):
            # The key is for the origin the adapter names. Same rule requests
            # applies to Authorization: dropped on a host, scheme or port
            # change, except an http->https upgrade on the default ports.
            headers = {k: v for k, v in headers.items() if k.lower() != API_KEY_HEADER}
        if response.status_code in (301, 302, 303):
            # What requests does: these turn a POST into a GET with no body.
            method, body, upload = "GET", None, None
        elif upload is not None:
            upload = files()
        url = next_url
    raise RedirectRefused(
        f"More than {MAX_REDIRECTS} redirects from the Unstructured API"
    )
