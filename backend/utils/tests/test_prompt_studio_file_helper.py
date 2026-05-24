"""Tests for the streaming write helper.

The helper's upload entry points (``PromptStudioFileHelper.upload_for_ide``,
``upload_converted_for_ide``) must:

- Keep the legacy bytes-input branch single-shot (preserves caller
  contract for converted-PDF flows that pass ``bytes``).
- For file-like inputs (Django ``UploadedFile``), open the destination
  via the underlying fsspec handle with ``block_size`` set so providers
  use their native multipart upload primitive (bounded RAM hold).
- Iterate via ``chunks()`` when present (Django uploads), otherwise
  fall back to fixed-size ``read()`` blocks.
- Abort the partial multipart upload on mid-stream exceptions so we
  don't leak orphaned upload parts in S3/GCS.

Tests target the ``streaming_writer`` module directly so they don't
boot the full Django settings chain via the calling helper. Pure pytest
with hand-rolled fakes — no ``unittest.mock`` dependency.
"""

from __future__ import annotations

import io
from typing import Any, Callable

import pytest

from utils.file_storage.helpers.streaming_writer import (
    STREAMING_CHUNK_SIZE,
    write_streaming,
)


class FakeHandle:
    """Hand-rolled fsspec-handle stand-in.

    Captures every ``write(chunk)`` call so tests can assert chunk size
    and ordering. Optional ``write_side_effect`` lets a test inject a
    failure mid-stream to exercise the abort path. ``abort_methods``
    controls which abort hook(s) the handle exposes — different fsspec
    providers expose different names, so tests parametrise.
    """

    def __init__(
        self,
        write_side_effect: Callable[[bytes], None] | None = None,
        close_side_effect: Callable[[], None] | None = None,
        abort_methods: tuple[str, ...] = ("abort_mpu",),
    ) -> None:
        self.writes: list[bytes] = []
        self.closed: int = 0
        self.aborts: list[str] = []
        self._write_side_effect = write_side_effect
        self._close_side_effect = close_side_effect
        for method_name in abort_methods:
            setattr(
                self,
                method_name,
                lambda name=method_name: self.aborts.append(name),
            )

    def write(self, chunk: bytes) -> None:
        if self._write_side_effect is not None:
            self._write_side_effect(chunk)
        self.writes.append(chunk)

    def close(self) -> None:
        self.closed += 1
        if self._close_side_effect is not None:
            self._close_side_effect()


class FakeFs:
    """Stand-in for ``fs_instance.fs`` — only needs ``open()``."""

    def __init__(self, handle: FakeHandle) -> None:
        self._handle = handle
        self.open_calls: list[dict[str, Any]] = []

    def open(self, path: str, mode: str, block_size: int) -> FakeHandle:
        self.open_calls.append({"path": path, "mode": mode, "block_size": block_size})
        return self._handle


class FakeStorage:
    """Stand-in for the ``FileStorage`` wrapper passed to the helper.

    Mirrors only the two attributes the helper actually touches:
    ``write`` (bytes fast-path) and ``fs`` (streaming path).
    """

    def __init__(self, handle: FakeHandle | None = None) -> None:
        self.write_calls: list[dict[str, Any]] = []
        self.fs = FakeFs(handle) if handle is not None else None

    def write(self, *, path: str, mode: str, data: bytes) -> None:
        self.write_calls.append({"path": path, "mode": mode, "data": data})


class UploadedFileLike:
    """Mimics ``django.core.files.uploadedfile.UploadedFile.chunks``."""

    def __init__(self, payload: bytes, chunk_size: int) -> None:
        self._payload = payload
        self._chunk_size = chunk_size
        self.chunks_called_with: int | None = None

    def chunks(self, chunk_size: int = 64 * 1024):
        self.chunks_called_with = chunk_size
        for i in range(0, len(self._payload), chunk_size):
            yield self._payload[i : i + chunk_size]


@pytest.fixture
def handle() -> FakeHandle:
    return FakeHandle()


@pytest.fixture
def storage(handle: FakeHandle) -> FakeStorage:
    return FakeStorage(handle=handle)


def test_bytes_input_uses_single_shot_write(storage: FakeStorage) -> None:
    write_streaming(storage, "/p/file.pdf", b"abc")

    assert storage.write_calls == [
        {"path": "/p/file.pdf", "mode": "wb", "data": b"abc"}
    ]
    assert storage.fs.open_calls == []


def test_bytes_input_skips_fs_open_even_if_present(handle: FakeHandle) -> None:
    storage = FakeStorage(handle=handle)
    write_streaming(storage, "/p/file.pdf", b"abc")

    assert handle.writes == []
    assert handle.closed == 0


def test_uploaded_file_streams_via_chunks(
    storage: FakeStorage, handle: FakeHandle
) -> None:
    payload = b"PDFBYTES" * 10_000
    upload = UploadedFileLike(payload, chunk_size=STREAMING_CHUNK_SIZE)

    write_streaming(storage, "/p/file.pdf", upload)

    assert storage.fs.open_calls == [
        {"path": "/p/file.pdf", "mode": "wb", "block_size": STREAMING_CHUNK_SIZE}
    ]
    assert b"".join(handle.writes) == payload
    assert upload.chunks_called_with == STREAMING_CHUNK_SIZE
    assert handle.closed == 1
    assert storage.write_calls == []


def test_file_like_without_chunks_falls_back_to_read(
    storage: FakeStorage, handle: FakeHandle
) -> None:
    payload = b"X" * (STREAMING_CHUNK_SIZE + 17)
    # Plain BytesIO has no .chunks() — exercises the read() fallback.
    file_like = io.BytesIO(payload)

    write_streaming(storage, "/p/file.bin", file_like)

    assert b"".join(handle.writes) == payload
    assert handle.closed == 1


def test_streaming_error_triggers_abort_mpu(storage: FakeStorage) -> None:
    def boom(_: bytes) -> None:
        raise RuntimeError("connection reset")

    failing = FakeHandle(write_side_effect=boom, abort_methods=("abort_mpu",))
    storage.fs = FakeFs(failing)

    with pytest.raises(RuntimeError, match="connection reset"):
        write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"abc" * 100, 8))

    assert failing.aborts == ["abort_mpu"]
    assert failing.closed == 1


def test_streaming_error_falls_back_to_discard_when_no_abort_mpu(
    storage: FakeStorage,
) -> None:
    def boom(_: bytes) -> None:
        raise RuntimeError("broken pipe")

    failing = FakeHandle(write_side_effect=boom, abort_methods=("discard",))
    storage.fs = FakeFs(failing)

    with pytest.raises(RuntimeError, match="broken pipe"):
        write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 32, 8))

    assert failing.aborts == ["discard"]
    assert failing.closed == 1


def test_streaming_writes_one_chunk_at_a_time_not_coalesced(
    storage: FakeStorage, handle: FakeHandle
) -> None:
    """Catches the 'collapse chunks into one bytes blob' regression.

    A 4-chunk generator source must produce 4 distinct ``write`` calls of
    ``<= chunk_size`` each — proves the helper isn't accumulating in a
    single buffer before flushing.
    """

    class _GenSource:
        def chunks(self, chunk_size: int = 64 * 1024):
            for _ in range(4):
                yield b"Z" * STREAMING_CHUNK_SIZE

    write_streaming(storage, "/p/big.pdf", _GenSource())

    assert len(handle.writes) == 4
    assert all(len(chunk) <= STREAMING_CHUNK_SIZE for chunk in handle.writes)


def test_unknown_abort_method_does_not_mask_original_error(
    storage: FakeStorage, caplog: pytest.LogCaptureFixture
) -> None:
    """If the provider exposes neither abort hook, the original exception
    must propagate cleanly and we must log the leak warning.
    """

    def boom(_: bytes) -> None:
        raise RuntimeError("primary failure")

    failing = FakeHandle(write_side_effect=boom, abort_methods=())
    storage.fs = FakeFs(failing)

    with caplog.at_level(
        "WARNING", logger="utils.file_storage.helpers.streaming_writer"
    ):
        with pytest.raises(RuntimeError, match="primary failure"):
            write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 8, 4))

    assert failing.aborts == []
    assert any("orphaned upload possible" in rec.message for rec in caplog.records)
    assert failing.closed == 1


def test_non_callable_chunks_attr_uses_read_fallback(
    storage: FakeStorage, handle: FakeHandle
) -> None:
    """A data attribute named ``chunks`` (not a method) must not be
    invoked — fall back to read-based iteration instead.
    """

    class _DataAttrChunks:
        # Intentionally a non-callable attribute, mimicking a class that
        # happens to expose a `chunks` data field.
        chunks = "not callable"

        def __init__(self, payload: bytes) -> None:
            self._payload = payload
            self._pos = 0

        def read(self, n: int = -1) -> bytes:
            if n < 0:
                chunk = self._payload[self._pos :]
                self._pos = len(self._payload)
            else:
                chunk = self._payload[self._pos : self._pos + n]
                self._pos += len(chunk)
            return chunk

    source = _DataAttrChunks(b"abcdefgh")
    write_streaming(storage, "/p/file.bin", source)

    assert b"".join(handle.writes) == b"abcdefgh"
    assert handle.closed == 1


def test_close_failure_on_success_path_propagates(
    storage: FakeStorage,
) -> None:
    """Provider-native multipart commits happen inside ``close()`` — a
    close failure on the success path means the upload did not finalize.
    The caller must see the error, not a silent success.
    """

    def fail_close() -> None:
        raise RuntimeError("multipart commit failed")

    failing = FakeHandle(close_side_effect=fail_close)
    storage.fs = FakeFs(failing)

    with pytest.raises(RuntimeError, match="multipart commit failed"):
        write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 8, 4))

    assert failing.closed == 1
    assert failing.aborts == []  # success path doesn't abort


def test_close_failure_after_write_error_does_not_mask_original(
    storage: FakeStorage, caplog: pytest.LogCaptureFixture
) -> None:
    """When the write loop already raised, a subsequent close failure
    must be logged and swallowed so the *original* exception reaches
    the caller intact."""

    def fail_write(_: bytes) -> None:
        raise RuntimeError("primary write failure")

    def fail_close() -> None:
        raise RuntimeError("secondary close failure")

    failing = FakeHandle(
        write_side_effect=fail_write,
        close_side_effect=fail_close,
        abort_methods=("abort_mpu",),
    )
    storage.fs = FakeFs(failing)

    with caplog.at_level(
        "WARNING", logger="utils.file_storage.helpers.streaming_writer"
    ):
        with pytest.raises(RuntimeError, match="primary write failure"):
            write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 8, 4))

    assert failing.aborts == ["abort_mpu"]
    assert failing.closed == 1
    assert any(
        "close after aborted streaming write failed" in rec.message
        for rec in caplog.records
    )


# Integration smoke (wiring upload_for_ide → write_streaming) is not
# unit-testable without booting Django settings (the helper transitively
# imports file_management → backend.__init__ → celery → settings). The
# call-site is a one-line delegation; coverage of the streaming behaviour
# above is sufficient. End-to-end behaviour is verified via the SDK
# migration smoke run on a real stack.
