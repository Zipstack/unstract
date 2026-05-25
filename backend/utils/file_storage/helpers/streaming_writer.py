"""Chunked write helper for FileStorage-backed uploads."""

from __future__ import annotations

import logging
from typing import Any

# Above the 5 MiB S3/GCS minimum for multipart parts; low enough to keep
# part count tractable for ~100 MB inputs.
STREAMING_CHUNK_SIZE = 8 * 1024 * 1024

logger = logging.getLogger(__name__)


def write_streaming(fs_instance: Any, file_path: str, file_data: Any) -> None:
    """Write file_data to file_path without buffering the full payload.

    On failure, remove file_path so no partial object is left at the
    final path. Unfinished multipart parts on object stores are reaped
    by the bucket's lifecycle policy.
    """
    if isinstance(file_data, bytes):
        try:
            fs_instance.write(path=file_path, mode="wb", data=file_data)
        except Exception:
            _remove_file(fs_instance, file_path)
            raise
        return

    out = fs_instance.fs.open(file_path, mode="wb", block_size=STREAMING_CHUNK_SIZE)
    try:
        chunks_iter = (
            file_data.chunks(chunk_size=STREAMING_CHUNK_SIZE)
            if callable(getattr(file_data, "chunks", None))
            else iter(lambda: file_data.read(STREAMING_CHUNK_SIZE), b"")
        )
        for chunk in chunks_iter:
            out.write(chunk)
    except Exception:
        try:
            out.close()
        except Exception:
            pass
        _remove_file(fs_instance, file_path)
        raise
    # On success, propagate close() errors — provider multipart commits
    # happen here, so a failure means the upload did not finalize.
    out.close()


def _remove_file(fs_instance: Any, file_path: str) -> None:
    try:
        fs_instance.fs.rm(file_path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("cleanup rm failed for %s: %s", file_path, e)
