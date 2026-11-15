import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

from unstract.core.mime_gate import classify_file_path

SPILL_CHUNK_SIZE = 1024 * 1024


class UploadSpillError(RuntimeError):
    """Local disk could not take a copy of an upload to classify it.

    Not an OSError on purpose: callers treat OSError as a fault in one upload's
    bytes, while a full or unwritable temp dir fails every upload alike.
    """


@contextmanager
def _disk_fault() -> Iterator[None]:
    try:
        yield
    except OSError as exc:
        raise UploadSpillError(str(exc)) from exc


def detect_upload_mime_type(file: IO[bytes]) -> str:
    """Classify an upload from its own bytes, as LLMWhisperer would.

    The multipart Content-Type is supplied by the caller and never verified, so
    it cannot decide what is allowed in. The upload is left at its start.
    """
    temporary_file_path = getattr(file, "temporary_file_path", None)
    if temporary_file_path is not None:
        return classify_file_path(temporary_file_path())

    file.seek(0)
    with _disk_fault():
        spill = tempfile.NamedTemporaryFile(suffix=".upload")
    # Reads from the upload stay outside _disk_fault: they fail this file only.
    try:
        while chunk := file.read(SPILL_CHUNK_SIZE):
            with _disk_fault():
                spill.write(chunk)
        with _disk_fault():
            spill.flush()
        return classify_file_path(spill.name)
    finally:
        file.seek(0)
        # Closing flushes again, so it can fail the same way the flush did.
        with _disk_fault():
            spill.close()
