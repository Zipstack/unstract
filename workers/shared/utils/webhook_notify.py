"""Terminal-state webhook delivery for Agent-KV (spec §6.7).

The egress decision is NOT made here. It belongs to
``unstract.core.network.ssrf``, the single place in the codebase that decides
whether a tenant-supplied URL may be dialled -- the same guard behind the
prompt-postprocessing and pipeline-notification sinks, which exists (per its own
docstring) "so a new sink does not carry its own copy of the rules".

This module shipped with its own ``_host_is_public``, built from negative
``ipaddress`` flags. Greptile review #4 asked for the shared guard on the
grounds that a NAT64 literal such as ``64:ff9b::7f00:1`` -- the RFC 6052
prefix carrying 127.0.0.1 in its low 32 bits -- slipped past it. **That
specific claim does not hold**: on the runtime this worker uses (3.12),
``ipaddress`` reports ``is_reserved`` for ``64:ff9b::/96``, so the local guard
already refused it. Verified against 3.12.9 rather than assumed.

The move is still right, for the reasons the local copy's existence was wrong:

- It refused in the WRONG DIRECTION too. ``64:ff9b::5db8:d822`` embeds the
  public 93.184.216.34 -- a legitimate destination for a deployment with a
  NAT64 route -- and the same ``is_reserved`` flag refused that as well. The
  shared guard re-checks the embedded IPv4 (``_EMBEDS_IPV4``) and so separates
  the two cases instead of rejecting the prefix wholesale.
- Its NAT64 refusal was ACCIDENTAL. ``is_reserved`` is not an SSRF control; it
  is a version-dependent table (its IPv6 entries have moved between CPython
  releases), and nothing recorded that this guard leaned on it. The shared
  guard refuses on ``is_global`` -- an allowlist maintained against the IANA
  registries -- plus an explicit embedded-IPv4 re-check.
- Enumerating what to refuse misses whatever belongs to none of the flags, and
  this copy had already been patched once for RFC 6598 shared address space for
  exactly that reason. The shared guard gets that range from ``is_global`` for
  free, which also retires the hardcoded ``100.64.0.0`` SonarCloud flagged.
- It also brings rules this sink never had: ``*.localhost`` decided without a
  resolver, credentials-in-URL, and the urlparse/urllib3 host disagreement that
  determines which host the socket actually connects to.

Residual accepted risk, unchanged and shared with every other sink: DNS is
resolved for the check and again by ``requests``, so a rebinding window exists.
The control for that is pod egress policy, not application code. The payload
carries only {job_id, status} and the response body is never read.
"""

import json
import logging

import requests

from unstract.core.network.ssrf import is_safe_webhook_url, safe_host

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def send_webhook(
    url: str, payload: dict, *, allow_http: bool = False, allow_insecure: bool = False
) -> bool:
    """``allow_insecure`` waives BOTH guards (http scheme and non-public host).

    Test/dev stacks only -- it exists so the e2e lane can deliver to a
    receiver on the compose host (host.docker.internal is a private
    address). Production never sets it; the SSRF guards stay mandatory.
    """
    try:
        if allow_insecure:
            # Scheme and destination both unchecked: this is the e2e escape
            # hatch, and the only path on which `requests.post` is reached
            # without the shared guard having approved the URL.
            pass
        elif not is_safe_webhook_url(
            url, allowed_schemes=("http", "https") if allow_http else ("https",)
        ):
            # is_safe_webhook_url already logged the refusal reason and host.
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
        logger.warning("webhook delivery failed (host=%s)", safe_host(url), exc_info=True)
        return False
