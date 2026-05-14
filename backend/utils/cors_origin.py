"""CORS origin helpers used by Django settings and SocketIO log events.

Kept free of Django imports so the matching/normalization logic can be unit
tested without bootstrapping the full project.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


class RegexOrigin:
    """Origin pattern that compares to strings via regex match.

    python-socketio enforces CORS with ``origin in allowed_origins`` during the
    engine.io handshake — overriding ``__eq__`` lets a single list entry cover
    a wildcard subdomain so bad origins are rejected before ``connect`` runs.

    Instances are intentionally unhashable: a hashable object must satisfy
    ``a == b ⇒ hash(a) == hash(b)``, but ``__eq__`` here is asymmetric across
    types (matches many strings, hashes only one pattern). Any code that put
    one in a ``set``/``frozenset`` would silently break the CORS gate, so
    ``__hash__`` is disabled to fail loud at construction time instead.

    ``fullmatch`` (not ``match``) is used so ``$`` doesn't permit a trailing
    newline — defense in depth even though WSGI strips them upstream.
    """

    def __init__(self, pattern: str) -> None:
        self._regex = re.compile(pattern)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self._regex.fullmatch(other) is not None
        return NotImplemented

    __hash__ = None  # see class docstring


def normalize_web_app_origin(env_value: str) -> tuple[str, str, str]:
    """Parse and canonicalize ``WEB_APP_ORIGIN_URL`` for CORS/CSRF allow-lists.

    Returns ``(origin, wildcard_origin, subdomain_regex)``:

    - ``origin``: ``scheme://host[:port]`` form. Hostname is lowercased and
      explicit default ports (:80 for http, :443 for https) are dropped, so
      it matches what browsers serialize per RFC 6454.
    - ``wildcard_origin``: same with a literal ``*.`` subdomain prefix, for
      Django's ``CSRF_TRUSTED_ORIGINS`` (which fnmatches ``*``).
    - ``subdomain_regex``: anchored pattern matching any subdomain of the
      configured netloc, for ``CORS_ALLOWED_ORIGIN_REGEXES`` and SocketIO
      via ``RegexOrigin``.

    Raises:
        ValueError: if the env value is not an http(s) URL with a host.
    """
    parsed = urlparse(env_value)
    # `parsed.port` is a property that raises ValueError on malformed/out-of-range
    # ports (e.g. `:abc`, `:99999`). Catch it here so misconfig surfaces with the
    # same actionable message as every other validation failure.
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(
            f"WEB_APP_ORIGIN_URL must be of the form http(s)://host[:port], "
            f"got: {parsed.geturl()!r}"
        ) from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            f"WEB_APP_ORIGIN_URL must be of the form http(s)://host[:port], "
            f"got: {parsed.geturl()!r}"
        )
    default_port = {"http": 80, "https": 443}[parsed.scheme]
    netloc = parsed.hostname
    if port and port != default_port:
        netloc = f"{netloc}:{port}"
    origin = f"{parsed.scheme}://{netloc}"
    wildcard = f"{parsed.scheme}://*.{netloc}"
    subdomain_regex = rf"^{re.escape(parsed.scheme)}://[^/]+\.{re.escape(netloc)}$"
    return origin, wildcard, subdomain_regex
