"""Terminal-state webhook delivery with SSRF guards (spec §6.7).

Residual accepted risk (documented in the spec): DNS is resolved for the
check and again by requests — a rebinding window exists. The payload carries
only {job_id, status}; the response body is never read.
"""

import ipaddress
import json
import logging
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10

# RFC 6598 Shared Address Space (CGNAT), 100.64.0.0/10: `ipaddress.is_private`
# does NOT cover this range (verified on py3.12) even though it's non-public
# address space carrier-grade NATs route internally, so it must be checked
# separately or a host resolving into it slips past every other guard below.
# (IPv6 unique-local fc00::/7 IS covered by `is_private`, so needs no
# separate check.)
_CGNAT_RANGE = ipaddress.ip_network("100.64.0.0/10")


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
            or ip in _CGNAT_RANGE
        ):
            return False
    return True


def send_webhook(
    url: str, payload: dict, *, allow_http: bool = False, allow_insecure: bool = False
) -> bool:
    """``allow_insecure`` waives BOTH guards (http scheme and non-public host).

    Test/dev stacks only -- it exists so the e2e lane can deliver to a
    receiver on the compose host (host.docker.internal is a private
    address). Production never sets it; the SSRF guards stay mandatory.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" and not (
            (allow_http or allow_insecure) and parsed.scheme == "http"
        ):
            logger.warning("webhook refused: scheme %r", parsed.scheme)
            return False
        if not parsed.hostname:
            logger.warning("webhook refused: no host")
            return False
        if not allow_insecure and not _host_is_public(parsed.hostname):
            logger.warning("webhook refused: non-public host")
            return False
        resp = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
            allow_redirects=False,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        logger.warning("webhook delivery failed", exc_info=True)
        return False
