"""Chunked write helper for FileStorage-backed uploads.

Lives outside ``prompt_studio_file_helper`` so it can be unit-tested
without triggering Django settings boot (the helper transitively imports
``file_management`` and hence the whole settings chain).
"""

from __future__ import annotations

import logging
from typing import Any

# Bounds per-write RAM hold for large uploads. Matches fsspec's
# resumable/multipart minimums (GCS/S3 require >=5 MB parts); we go
# higher to keep part count tractable for ~100 MB inputs.
STREAMING_CHUNK_SIZE = 8 * 1024 * 1024

logger = logging.getLogger(__name__)


def write_streaming(fs_instance: Any, file_path: str, file_data: Any) -> None:
    """Write ``file_data`` to ``file_path`` without buffering the entire
    payload in memory.

    ``bytes`` payloads stay single-shot — existing callers pass already-
    materialised bytes (converted-PDF path), and re-streaming would just
    add overhead. For file-like inputs (Django ``UploadedFile``,
    ``IOBase``) we iterate via the source's own ``chunks()`` when
    available, otherwise read into fixed-size blocks. The destination is
    opened directly via the underlying fsspec handle so the provider can
    use its native multipart upload primitive instead of buffering.
    """
    if isinstance(file_data, bytes):
        fs_instance.write(path=file_path, mode="wb", data=file_data)
        return

    out = None
    success = False
    try:
        out = fs_instance.fs.open(file_path, mode="wb", block_size=STREAMING_CHUNK_SIZE)
        chunks_iter = (
            file_data.chunks(chunk_size=STREAMING_CHUNK_SIZE)
            if hasattr(file_data, "chunks")
            else iter(lambda: file_data.read(STREAMING_CHUNK_SIZE), b"")
        )
        for chunk in chunks_iter:
            out.write(chunk)
        success = True
    except Exception:
        if out is not None:
            _safe_abort(out, file_path)
        raise
    finally:
        if out is not None:
            if success:
                # Provider-native multipart commits happen inside close()
                # for s3fs/gcsfs/etc — a close failure here means the
                # upload did not finalize, so propagate it.
                out.close()
            else:
                try:
                    out.close()
                except Exception as close_err:  # pragma: no cover - close path
                    logger.warning(
                        "close after aborted streaming write failed for %s: %s",
                        file_path,
                        close_err,
                    )


def _safe_abort(handle: Any, file_path: str) -> None:
    """Best-effort multipart abort across providers.

    s3fs exposes ``abort_mpu`` on its file handle; gcsfs uses ``discard``.
    Local fs has nothing to abort (write was direct). Anything
    unrecognised is logged and ignored — masking the original exception
    is worse than potentially leaking an upload part.
    """
    for method_name in ("abort_mpu", "discard"):
        method = getattr(handle, method_name, None)
        if callable(method):
            try:
                method()
                return
            except Exception as e:  # pragma: no cover - abort path
                logger.warning(
                    "abort via %s failed for %s: %s", method_name, file_path, e
                )
                return
    logger.warning(
        "no multipart-abort hook on handle %s for %s; orphaned upload possible",
        type(handle).__name__,
        file_path,
    )
