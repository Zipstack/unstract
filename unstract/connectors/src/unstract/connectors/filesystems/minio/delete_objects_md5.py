"""Send ``Content-MD5`` on S3 ``DeleteObjects`` again (UN-4224).

botocore 1.36 replaced ``Content-MD5`` with a CRC32 flexible checksum on
``DeleteObjects``. MinIO older than RELEASE.2025-01-20 still requires
``Content-MD5`` for that call and rejects it with ``MissingContentMD5`` — which
breaks every bulk delete ``s3fs`` issues (``rm`` always goes through
``DeleteObjects``, even for a single key). The environment switches
(``AWS_REQUEST_CHECKSUM_CALCULATION=when_required``) do not help, because
``DeleteObjects`` is an operation that *requires* a checksum.

botocore's own ``conditionally_calculate_md5`` cannot be reused: it skips any
request that already carries a flexible checksum, which is exactly this case.
Sending both headers is accepted by AWS S3 and by every MinIO version.

The handler is appended to ``botocore.handlers.BUILTIN_HANDLERS``, so it reaches
every session created afterwards — botocore, boto3 and the aiobotocore sessions
``s3fs`` creates lazily on first use. Sessions created before this module is
imported are not affected.

unstract-sdk1 carries an identical copy (``unstract.sdk1.patches.
s3_delete_objects_md5``) — this package does not depend on sdk1, so it cannot
import it. Whichever is imported first registers the handler, the other is a
no-op. Keep the two in sync.
"""

import base64
import hashlib
from typing import Any

import botocore.handlers

_EVENT = "before-call.s3.DeleteObjects"
_REGISTERED_FLAG = "_unstract_delete_objects_md5_registered"


def add_content_md5(params: dict[str, Any], **kwargs: Any) -> None:  # noqa: ANN401
    """Add ``Content-MD5`` to a ``DeleteObjects`` request that lacks one."""
    headers = params["headers"]
    if "Content-MD5" in headers:
        return
    # S3 Express One Zone buckets reject MD5.
    endpoint = params.get("context", {}).get("endpoint_properties", {})
    if endpoint.get("backend") == "S3Express":
        return
    body = params.get("body")
    if isinstance(body, str):
        body = body.encode("utf-8")
    if not isinstance(body, bytes | bytearray):
        return
    digest = hashlib.md5(body, usedforsecurity=False).digest()
    headers["Content-MD5"] = base64.b64encode(digest).decode("ascii")


def register() -> None:
    """Register :func:`add_content_md5` once per process."""
    if getattr(botocore.handlers, _REGISTERED_FLAG, False):
        return
    # Appended, so it runs after botocore's own `escape_xml_payload` handler for
    # this event has produced the final body the digest must cover.
    botocore.handlers.BUILTIN_HANDLERS.append((_EVENT, add_content_md5))
    setattr(botocore.handlers, _REGISTERED_FLAG, True)


register()
