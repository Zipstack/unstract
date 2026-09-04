"""Shared egress guard for user-supplied webhook URLs.

Both webhook sinks — prompt postprocessing and pipeline notifications — hand a
tenant-supplied URL to ``requests``. This module is the single place that
decides whether one may be dialled, so a new sink does not carry its own copy
of the rules.

``is_safe_webhook_url`` answers the yes/no question and logs the reason;
``webhook_url_refusal`` returns the reason, so a sink can tell a resolver
outage (retryable) from a URL that will never be allowed.

Note the ceiling: resolve-then-connect cannot cover a name that is re-resolved
to an internal address between the check and the socket. The control for that
is an egress policy on the worker pods, not application code.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import idna
from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_SCHEMES = ("http", "https")

# Refusal reasons. UNRESOLVABLE is the only transient one — a resolver outage
# clears on its own, so a sink may retry it. Every other reason is a property
# of the URL itself and cannot change between attempts.
UNRESOLVABLE = "unresolvable"
REFUSED_EMPTY_URL = "empty-url"
REFUSED_UNPARSEABLE = "unparseable-url"
REFUSED_SCHEME = "scheme-not-allowed"
REFUSED_CREDENTIALS = "credentials-in-url"
REFUSED_PARSER_DISAGREEMENT = "parser-disagreement"
REFUSED_EMPTY_HOST = "empty-host"
REFUSED_INTERNAL_LITERAL = "internal-literal"
REFUSED_NON_PUBLIC = "non-public-address"

# RFC 6761 reserves these to loopback, so no lookup is needed to know where
# they point.
_LOOPBACK_NAMES = ("localhost",)

# Ranges IANA marks as not globally reachable that ``is_global`` still admits,
# because the stdlib's copy of the registries predates them or omits them.
# Multicast is handled separately in ``_is_public`` via ``is_multicast``.
# These are registry entries, not deployment addresses: they name ranges this
# guard must refuse, so they are hardcoded by definition. NOSONAR
_NOT_GLOBALLY_REACHABLE = (
    ipaddress.ip_network("192.88.99.0/24"),  # NOSONAR - 6to4 relay anycast (RFC 7526)
    ipaddress.ip_network("5f00::/16"),  # NOSONAR - SRv6 SIDs (RFC 9602)
)


def _normalize_host(host: str | None) -> str:
    """Reduce a host to the form the transport will dial.

    urllib3 keeps the brackets on an IPv6 literal and punycodes a unicode host;
    ``urlparse`` does neither. Comparing the raw strings would refuse both of
    those legitimate URLs.

    The encoding mirrors ``urllib3.util.url._idna_encode`` exactly — ASCII hosts
    are only lowercased, non-ASCII hosts are encoded per label with the ``idna``
    package. The stdlib ``"idna"`` codec is *not* interchangeable here: it is
    IDNA-2003 with nameprep, so it maps ``faß.de`` to ``fass.de`` where the
    transport produces ``xn--fa-hia.de``, and the parser-agreement check below
    would refuse every such host.
    """
    if not host:
        return ""
    host = host.strip().strip("[]").rstrip(".").lower()
    if host.isascii():
        return host
    try:
        return ".".join(
            idna.encode(label, strict=True, std3_rules=True).decode("ascii")
            for label in host.split(".")
        )
    except (idna.IDNAError, UnicodeError):
        # Not IDNA-encodable (empty label, over-long label, disallowed
        # codepoint). Compare as-is; the parsers still have to agree for the
        # URL to be accepted.
        return host


def _as_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a host that is an address literal, or None if it is a name.

    ``ipaddress.ip_address`` only accepts dotted-quad IPv4, so on its own it
    reads ``2130706433``, ``0177.0.0.1`` and ``127.1`` as hostnames — all three
    are ``127.0.0.1`` to the resolver. ``inet_aton`` accepts the same legacy
    forms the C resolver does, which is what the transport ends up using.
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ipaddress.AddressValueError):
        return None


def _resolve(host: str) -> set[str]:
    """Return every IP the host resolves to, or an empty set on failure."""
    literal = _as_ip(host)
    if literal is not None:
        return {str(literal)}
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

    ``is_global`` is the base check because it is an allowlist maintained
    against the IANA registries; enumerating the negative flags instead misses
    ranges that belong to none of them, such as RFC 6598 shared address space.
    It is not sufficient alone — it reports multicast and the
    ``_NOT_GLOBALLY_REACHABLE`` ranges as global, so those are refused here.
    """
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if not ip.is_global or ip.is_multicast:
        return False
    # ``in`` is version-safe: _BaseNetwork.__contains__ returns False on a
    # version mismatch rather than raising, so no explicit guard is needed.
    return not any(ip in net for net in _NOT_GLOBALLY_REACHABLE)


def is_retryable_refusal(reason: str | None) -> bool:
    """Whether retrying a refusal could ever produce a different outcome.

    Only :data:`UNRESOLVABLE` can: a resolver outage clears on its own. Every
    other reason is a property of the URL itself. Kept next to the reasons so a
    new one has to be classified here rather than at each sink.
    """
    return reason == UNRESOLVABLE


def webhook_url_refusal(
    url: str | None,
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES,
    resolve: bool = True,
) -> str | None:
    """Why ``url`` may not be dialled, or None if it may.

    Same checks as :func:`is_safe_webhook_url`; use this one where the sink
    needs to act on *why* it was refused. Compare the result against
    :data:`UNRESOLVABLE` to separate a resolver outage, which may clear, from a
    refusal that never will.
    """
    if not url:
        return REFUSED_EMPTY_URL

    try:
        parsed = urlparse(url)
    except ValueError:
        return REFUSED_UNPARSEABLE

    if parsed.scheme not in allowed_schemes:
        return REFUSED_SCHEME

    # Credentials in the URL are the vehicle for the parser confusion below and
    # have no legitimate use on a webhook target.
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        return REFUSED_CREDENTIALS

    try:
        transport_host = parse_url(url).host
    except LocationParseError:
        # The transport cannot parse it, so nothing here can predict where it
        # would connect.
        return REFUSED_UNPARSEABLE

    # ``urlparse`` decided the host above; urllib3 is what the transport under
    # ``requests`` actually dials. Where the two disagree, the host approved
    # here is not the host the socket connects to. Comparing them is an
    # invariant rather than a list of characters to reject, so it holds as
    # either parser changes.
    host = _normalize_host(parsed.hostname)
    if host != _normalize_host(transport_host):
        return REFUSED_PARSER_DISAGREEMENT

    if not host:
        return REFUSED_EMPTY_HOST

    literal = _as_ip(host)

    if not resolve:
        # No DNS on this path. An address literal is still checked, since that
        # needs no lookup and is how most internal targets are written — in any
        # of the encodings ``_as_ip`` understands, not just dotted-quad. A
        # hostname is accepted here and caught at the sink.
        if literal is not None and not _is_public(str(literal)):
            return REFUSED_INTERNAL_LITERAL
        if host in _LOOPBACK_NAMES or host.endswith(".localhost"):
            return REFUSED_INTERNAL_LITERAL
        return None

    # Resolve the normalized host: that is the canonical form the transport
    # ends up dialling, so the addresses checked here are the ones used.
    addrs = _resolve(host)
    if not addrs:
        return UNRESOLVABLE

    if not all(_is_public(addr) for addr in addrs):
        return REFUSED_NON_PUBLIC

    return None


def is_safe_webhook_url(
    url: str | None,
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES,
    resolve: bool = True,
) -> bool:
    """Whether ``url`` may be dialled from inside the network.

    Leave ``resolve`` on at the sinks — that is the real control. Turn it off on
    request-handling threads: ``socket.getaddrinfo`` honours no timeout, so a
    slow or hostile resolver would stall the worker serving the request. With it
    off the syntactic checks still run and an address literal is still refused,
    but a hostname that resolves inward is accepted here and caught at the sink.
    """
    reason = webhook_url_refusal(url, allowed_schemes=allowed_schemes, resolve=resolve)
    if reason is None:
        return True

    # The host, not the URL: a webhook URL routinely carries a token in its
    # query string, and this line goes to shared logs. Without the reason,
    # support cannot tell a scheme rejection from a resolver outage — five
    # different remediations behind one message.
    logger.warning(
        "Refusing webhook URL: %s (host=%s)",
        reason,
        safe_host(url),
    )
    return False


def safe_host(url: str | None) -> str:
    """The host of ``url`` for logging, never the path or query string.

    Public because every sink that logs a refusal needs it, and a second copy
    is a second chance to drop the ``ValueError`` guard on a malformed literal.
    """
    try:
        return urlparse(url or "").hostname or "<none>"
    except ValueError:
        return "<unparseable>"
