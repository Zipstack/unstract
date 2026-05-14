"""URL safety helpers (SSRF protection).

Shared between the workers executor and the prompt-service answer-prompt
service because both need to validate webhook URLs before issuing
postprocessing callbacks.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def _resolve_host_addresses(host: str) -> set[str]:
    """Resolve a hostname or IP string to a set of IP address strings."""
    try:
        ipaddress.ip_address(host)
        return {host}
    except ValueError:
        pass
    try:
        return {
            sockaddr[0]
            for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
                host, None, type=socket.SOCK_STREAM
            )
        }
    except Exception:
        return set()


def is_safe_public_url(url: str) -> bool:
    """Validate a URL for use as an outbound webhook target (SSRF protection).

    Only HTTPS URLs are allowed, and the resolved host must not point to
    a private, loopback, link-local, reserved, or multicast address.
    All DNS records (A/AAAA) are resolved to prevent DNS rebinding
    attacks.
    """
    try:
        p = urlparse(url)
        if p.scheme not in ("https",):  # only HTTPS
            return False
        host = p.hostname or ""
        if host == "localhost":
            return False

        addrs = _resolve_host_addresses(host)
        if not addrs:
            return False

        for addr in addrs:
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                return False
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return False
        return True
    except Exception:
        return False
