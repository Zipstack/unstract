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


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def send_webhook(url: str, payload: dict, *, allow_http: bool = False) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" and not (allow_http and parsed.scheme == "http"):
            logger.warning("webhook refused: scheme %r", parsed.scheme)
            return False
        if not parsed.hostname or not _host_is_public(parsed.hostname):
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
