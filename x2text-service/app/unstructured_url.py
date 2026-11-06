"""Egress checks for the tenant-supplied Unstructured API URL.

The ``unstructured-url`` form field comes from an adapter any org user can
configure, and this service POSTs the uploaded document to it. The shared guard
in ``unstract.core.network.ssrf`` decides whether that URL may be dialled.

Whether a private, loopback or link-local destination is allowed depends on the
deployment. docker-compose (OSS) installs routinely run Unstructured on
localhost or a private host, so it is allowed when the setting is unset. A
deployment serving untrusted tenants must refuse it by setting
``UNSTRUCTURED_URL_ALLOW_PRIVATE=false``.

Where private destinations are refused, ``UNSTRUCTURED_URL_ALLOWED_HOSTS`` names
hosts that are exempt from that destination check: a comma-separated list of
exact hostnames, matched case-insensitively after trimming, with no wildcards,
ports or address ranges. A deployment that runs Unstructured in-cluster lists
that Service's name here. It is empty by default, so nothing is exempt, and it
is not consulted where private destinations are allowed. The scheme, credential
and parser-agreement checks still apply to an allowlisted host. Where private
destinations are allowed, credentials in the URL (basic auth in front of a
self-hosted Unstructured) are accepted, as they were before this guard. Because the
match is exact, list every form of the name that saved adapters use (short
name, FQDN), and set it no later than ``UNSTRUCTURED_URL_ALLOW_PRIVATE=false``,
or those adapters are refused in between.

Redirects follow the same rule. Where private destinations are allowed they
are followed as ``requests`` always did. Where they are refused, each hop is
checked with the same guard before it is dialled, up to ``MAX_REDIRECTS``.
The allowlist applies per hop: a redirect is followed only to a host that is
itself allowlisted or passes the destination check.

With private destinations refused, a name that is not allowlisted is resolved
here and again by ``requests``, so a name re-resolved to an internal address in
between is not caught. The control for that is an egress policy on the pods
(see ``ssrf.py``). An allowlisted name is not resolved here at all: it is
trusted to resolve wherever DNS points it.
"""

import logging
import math
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

from unstract.core.network.ssrf import (
    REFUSED_INTERNAL_LITERAL,
    REFUSED_NON_PUBLIC,
    REFUSED_UNPARSEABLE,
    UNRESOLVABLE,
    safe_host,
    webhook_url_refusal,
)

logger = logging.getLogger(__name__)

ALLOW_PRIVATE_ENV = "UNSTRUCTURED_URL_ALLOW_PRIVATE"
ALLOWED_HOSTS_ENV = "UNSTRUCTURED_URL_ALLOWED_HOSTS"
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


class RedirectRefused(Exception):
    """A redirect from the Unstructured API that will not be followed.

    The exception text is the detailed reason, for the log. What the caller
    sees is ``user_message``, a fixed string per subclass, so nothing from the
    exception reaches the response.
    """

    user_message = "Redirect refused: the Unstructured API redirected elsewhere"


class RedirectNotAllowed(RedirectRefused):
    user_message = (
        "Redirect refused: the Unstructured API redirected to a destination "
        "that is not allowed"
    )


class RedirectUnresolvable(RedirectRefused):
    # Unlike the others, this one can clear: the resolver may be down.
    user_message = (
        "Redirect refused: the host the Unstructured API redirected to could "
        "not be resolved"
    )


class RedirectUnparseable(RedirectRefused):
    user_message = "Redirect refused: the Unstructured API sent an unparseable Location"


class TooManyRedirects(RedirectRefused):
    user_message = f"Redirect refused: more than {MAX_REDIRECTS} redirects"


def allow_private() -> bool:
    """Whether private, loopback and link-local destinations are allowed.

    Unset or empty means allowed. Any other value that is not a recognised true
    value refuses them.
    """
    raw = os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower()
    return not raw or raw in _TRUE_VALUES


def allowed_hosts() -> frozenset[str]:
    """Hostnames exempt from the destination check when private is refused.

    Exact names, lower-cased, from a comma-separated list. Empty entries are
    dropped, so unset or empty means none.
    """
    raw = os.environ.get(ALLOWED_HOSTS_ENV, "")
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _is_allowlisted(url: str) -> bool:
    """Whether the host of ``url`` is exactly one of :func:`allowed_hosts`.

    An allowlisted name is trusted to resolve wherever DNS points it, private
    or not, so it must be a cluster-internal Service name that no org user can
    create or repoint. A name a tenant can influence, such as an external
    domain, would reopen the hole this guard closes.
    """
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    return bool(host) and host in allowed_hosts()


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


def _without_userinfo(url: str) -> str:
    r"""``url`` with any ``user:pass@`` removed, for the checks that follow it.

    The shared guard stops at its credential check, so the host checks after it
    (parser agreement, control characters, empty host) are run on this copy.
    The original URL, credentials included, is still what gets dialled.

    The copy is rebuilt the way ``urlparse`` reads the URL, which is not
    always how the transport reads it (``http://a@b\@c/`` is ``c`` to one and
    ``b`` to the other). So the copy is used only when urllib3, which the
    transport dials with, finds the same host in both. Otherwise ``url`` is
    returned unchanged and the guard refuses it as ``credentials-in-url``.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if "@" not in (parsed.netloc or ""):
        return url
    stripped = parsed._replace(netloc=parsed.netloc.rpartition("@")[2]).geturl()
    try:
        same_host = parse_url(url).host == parse_url(stripped).host
    except LocationParseError:
        return url
    return stripped if same_host else url


def refusal_reason(url: str) -> str | None:
    """The guard's reason ``url`` may not be dialled, or None if it may.

    The scheme and host-syntax checks always apply. Credentials in the URL
    (``user:pass@host``) are refused only when private destinations are not
    allowed. There they could steer the request to a host the guard did not
    approve. Where any destination is allowed they gain an attacker nothing,
    and a self-hosted Unstructured behind basic auth needs them, so the host
    checks run on the URL without its userinfo instead, unless removing it
    changes the host the transport would dial (see :func:`_without_userinfo`). The destination check
    applies only when private destinations are not allowed and the host is not
    in :func:`allowed_hosts`; otherwise no lookup is made here.
    """
    if allow_private():
        reason = webhook_url_refusal(_without_userinfo(url), resolve=False)
    elif _is_allowlisted(url):
        reason = webhook_url_refusal(url, resolve=False)
    else:
        reason = webhook_url_refusal(url)
    # resolve=False reports an internal literal (or localhost) as its last
    # check, after every syntactic one, so waiving it waives nothing else. On
    # the full guard this reason means a refused destination and stands.
    if reason == REFUSED_INTERNAL_LITERAL and (allow_private() or _is_allowlisted(url)):
        reason = None

    if reason is not None:
        # The host only: the URL can carry a key in its query string.
        logger.warning(
            "Refusing unstructured-url: %s (host=%s, %s=%s, %s=%s)",
            reason,
            safe_host(url),
            ALLOW_PRIVATE_ENV,
            allow_private(),
            # Operator-set Service names, not secrets. Shown so an entry that
            # can never match (one with a port or scheme, say) is visible.
            ALLOWED_HOSTS_ENV,
            ",".join(sorted(allowed_hosts())),
        )
    return reason


def refusal_message(url: str) -> str | None:
    """A message for the caller if ``url`` may not be dialled, else None."""
    reason = refusal_reason(url)
    if reason is None:
        return None
    if reason == UNRESOLVABLE:
        return "Unstructured URL host could not be resolved"
    if reason in (REFUSED_INTERNAL_LITERAL, REFUSED_NON_PUBLIC):
        return (
            "Unstructured URL points to a private, loopback or link-local "
            "address, which is not allowed on this deployment"
        )
    return f"Unstructured URL is not allowed ({reason})"


def _checked_redirect_target(url: str, response: requests.Response) -> str:
    """Where a redirect from ``url`` points, once the guard allows it.

    Raises:
        RedirectRefused: the Location cannot be parsed, its host does not
            resolve, or the guard refuses it.
    """
    try:
        next_url = urljoin(url, response.headers["Location"])
    except ValueError:
        raise RedirectUnparseable("unparseable Location") from None
    if reason := refusal_reason(next_url):
        if reason == UNRESOLVABLE:
            raise RedirectUnresolvable(reason)
        if reason == REFUSED_UNPARSEABLE:
            raise RedirectUnparseable(reason)
        raise RedirectNotAllowed(reason)
    return next_url


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
        # Redirects are followed by requests itself, as before the guard.
        return requests.request(
            "POST", url, headers=headers, data=data, files=files(), timeout=timeout
        )

    method, body, upload = "POST", data, files()
    # One session per call, so a cookie set by a hop goes with the next one
    # (as when requests follows redirects itself) and goes nowhere else.
    with requests.Session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            response = session.request(
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
            next_url = _checked_redirect_target(url, response)
            if session.should_strip_auth(url, next_url):
                # The key is for the origin the adapter names. Same rule
                # requests applies to Authorization: dropped on a host, scheme
                # or port change, except an http->https upgrade on the default
                # ports.
                headers = {
                    k: v for k, v in headers.items() if k.lower() != API_KEY_HEADER
                }
            if response.status_code in (301, 302, 303):
                # What requests does: these turn a POST into a GET with no body.
                method, body, upload = "GET", None, None
            elif upload is not None:
                upload = files()
            url = next_url
    raise TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")
