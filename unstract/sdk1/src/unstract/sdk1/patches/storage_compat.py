"""Keep the storage stack's wire behaviour stable across the boto3/gcsfs upgrade.

UN-4224 moved boto3/botocore from 1.34 to 1.43 and gcsfs to 2026.x. Both
changed defaults that reach every S3-compatible and GCS backend we talk to.
This module restores the previous behaviour in one place. It is loaded by
the sdk1 file-storage helper and by the MinIO and GCS connectors in
unstract-connectors; everything here is idempotent.

1. ``S3_CHECKSUM_CONFIG`` — botocore 1.36 made ``request_checksum_calculation``
   default to ``when_supported``. Over HTTPS, every PutObject / UploadPart then
   goes out as ``Content-Encoding: aws-chunked`` with a CRC32 trailer
   (``X-Amz-Content-SHA256: STREAMING-UNSIGNED-PAYLOAD-TRAILER``) — including to
   Unstract Cloud Storage, which is GCS's S3 interop API, and to MinIO behind
   TLS. ``when_required`` sends the plain payload-signed request boto3 1.34
   sent. Pass it as ``config_kwargs`` (s3fs) or ``botocore.config.Config``
   (boto3) wherever an S3 client is created.

2. ``Content-MD5`` on ``DeleteObjects`` — ``DeleteObjects`` *requires* a
   checksum, so ``when_required`` still sends CRC32 instead of ``Content-MD5``.
   MinIO older than RELEASE.2025-01-20 rejects that with ``MissingContentMD5``,
   which breaks every bulk delete ``s3fs`` issues (``rm`` always goes through
   ``DeleteObjects``, even for one key). botocore's own
   ``conditionally_calculate_md5`` cannot be reused: it skips requests that
   carry a flexible checksum, which is exactly this case. Sending both headers
   is accepted by AWS S3 and by every MinIO version. The handler is appended to
   ``botocore.handlers.BUILTIN_HANDLERS``, so it reaches every session created
   afterwards — botocore, boto3 and the aiobotocore sessions ``s3fs`` creates
   lazily on first use.

3. ``GCSFS_EXPERIMENTAL_ZB_HNS_SUPPORT=false`` — gcsfs 2026.x replaces
   ``gcsfs.GCSFileSystem`` (and fsspec's ``gcs`` protocol) with the
   experimental gRPC-backed ``ExtendedGcsFileSystem`` unless this is set. It
   only takes effect if set before gcsfs is first imported, so it is defaulted
   here (an explicit operator setting wins) and a warning is logged if gcsfs
   was already imported.
"""

import base64
import hashlib
import logging
import os
import sys
from typing import Any

import botocore.handlers

logger = logging.getLogger(__name__)

S3_CHECKSUM_CONFIG: dict[str, str] = {
    "request_checksum_calculation": "when_required",
    "response_checksum_validation": "when_required",
}

_EVENT = "before-call.s3.DeleteObjects"
_REGISTERED_FLAG = "_unstract_delete_objects_md5_registered"
_GCSFS_EXPERIMENTAL_ENV = "GCSFS_EXPERIMENTAL_ZB_HNS_SUPPORT"


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


def keep_core_gcsfs() -> None:
    """Keep gcsfs on its core ``GCSFileSystem`` unless an operator opted in."""
    os.environ.setdefault(_GCSFS_EXPERIMENTAL_ENV, "false")
    gcsfs = sys.modules.get("gcsfs")
    loaded_class = getattr(getattr(gcsfs, "GCSFileSystem", None), "__name__", "")
    if (
        loaded_class == "ExtendedGcsFileSystem"
        and os.environ[_GCSFS_EXPERIMENTAL_ENV] == "false"
    ):
        logger.warning(
            "gcsfs was imported before %s=false was applied and is using the "
            "experimental ExtendedGcsFileSystem.",
            _GCSFS_EXPERIMENTAL_ENV,
        )


register()
keep_core_gcsfs()
