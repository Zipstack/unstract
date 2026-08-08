"""Shared egress guard for user-supplied webhook URLs.

Both webhook sinks — prompt postprocessing and pipeline notifications — take a
URL from a tenant and hand it to ``requests``. This module is the single place
that decides whether such a URL may be dialled, so a new sink does not have to
carry its own copy of the rules.

Three things are checked, in order:

1. **Parser agreement.** This module reads the URL with ``urllib.parse`` while
   the transport underneath ``requests`` resolves it with ``urllib3``. The two
   do not always agree on the host, and where they disagree the URL is refused,
   because the host approved here is not the host the socket connects to.
   Comparing the two parsers is an invariant rather than a list of characters to
   reject, so it holds as either parser changes.
2. **Scheme and userinfo.** Anything outside the caller's allowlist is refused,
   as is a URL carrying credentials.
3. **Resolved address.** Every address the host resolves to must be publicly
   routable. Loopback, private, link-local (which covers the cloud metadata
   endpoints), reserved and multicast ranges are all refused.

Note the ceiling: resolve-then-connect cannot cover a name that is re-resolved
to an internal address between this check and the socket. The control for that
is an egress policy on the worker pods, not application code.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_SCHEMES = ("http", "https")


def _normalize_host(host: str | None) -> str:
    """Reduce a host to a form the two parsers can be compared on.

    urllib3 keeps the brackets on an IPv6 literal and punycodes a unicode host;
    ``urlparse`` does neither. Comparing the raw strings would refuse both of
    those legitimate URLs.
    """
    if not host:
        return ""
    host = host.strip().strip("[]").rstrip(".").lower()
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        # Not IDNA-encodable (empty label, over-long label). Compare as-is;
        # the parsers still have to agree for the URL to be accepted.
        return host


def _resolve(host: str) -> set[str]:
    """Return every IP the host resolves to, or an empty set on failure."""
    try:
        ipaddress.ip_address(host)
        return {host}
    except ValueError:
        pass
    try:
        return {
            sockaddr[0]
            for *_, sockaddr in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        }
    except (OSError, UnicodeError):
        # UnicodeError: getaddrinfo IDNA-encodes internally and raises, not
        # returns, on an over-long or empty label. Unresolvable either way.
        return set()


def _is_public(addr: str) -> bool:
    """Whether an address is globally routable.

    ``is_global`` is an allowlist maintained against the IANA special-purpose
    registries, so it stays correct as ranges are added. Enumerating the
    negative flags instead misses ranges that belong to none of them — RFC 6598
    shared address space (100.64.0.0/10) is private in practice but is not
    ``is_private``, ``is_reserved`` or any of the rest.
    """
    try:
        return ipaddress.ip_address(addr).is_global
    except ValueError:
        return False


def is_safe_webhook_url(
    url: str | None,
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES,
    resolve: bool = True,
) -> bool:
    """Whether ``url`` may be dialled from inside the network.

    Args:
        url: The tenant-supplied URL.
        allowed_schemes: Schemes to accept. Callers that already require TLS
            should pass ``("https",)`` rather than widening to the default.
        resolve: Whether to resolve the host and check every address. Leave it
            on at the sinks — that is the real control. Turn it off on request
            handling threads: ``socket.getaddrinfo`` honours no timeout, so a
            slow or hostile resolver would stall the worker serving the
            request. With it off, the syntactic checks still run and a literal
            internal IP is still refused; a hostname that resolves internally
            is caught at the sink instead.

    Returns:
        True only if the URL is well-formed, unambiguous to both parsers, and
        (when ``resolve`` is set) maps entirely to public addresses.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in allowed_schemes:
        return False

    # Credentials in the URL are the vehicle for the parser confusion above and
    # have no legitimate use on a webhook target.
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        return False

    try:
        transport_host = parse_url(url).host
    except LocationParseError:
        # The transport cannot parse it, so nothing here can predict where it
        # would connect.
        return False

    host = _normalize_host(parsed.hostname)
    if host != _normalize_host(transport_host):
        logger.warning("Refusing webhook URL: validator and transport disagree on host")
        return False

    if not host:
        return False

    if not resolve:
        # No DNS on this path. A literal address is still checked, since that
        # needs no lookup and is how most internal targets are written.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return True
        return _is_public(host)

    # Resolve the normalized host: that is the canonical form the transport
    # ends up dialling, so the addresses checked here are the ones used.
    addrs = _resolve(host)
    if not addrs:
        return False

    return all(_is_public(addr) for addr in addrs)
