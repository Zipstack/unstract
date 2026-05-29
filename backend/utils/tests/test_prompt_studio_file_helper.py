"""Tests for the streaming write helper."""

from __future__ import annotations

import io
from typing import Any, Callable

import pytest

from utils.file_storage.helpers.streaming_writer import (
    STREAMING_CHUNK_SIZE,
    write_streaming,
)


class FakeHandle:
    """Stand-in for an fsspec file handle. Records writes; lets tests
    inject failures via ``write_side_effect`` / ``close_side_effect``."""

    def __init__(
        self,
        write_side_effect: Callable[[bytes], None] | None = None,
        close_side_effect: Callable[[], None] | None = None,
    ) -> None:
        self.writes: list[bytes] = []
        self.closed: int = 0
        self._write_side_effect = write_side_effect
        self._close_side_effect = close_side_effect

    def write(self, chunk: bytes) -> None:
        if self._write_side_effect is not None:
            self._write_side_effect(chunk)
        self.writes.append(chunk)

    def close(self) -> None:
        self.closed += 1
        if self._close_side_effect is not None:
            self._close_side_effect()


class FakeFs:
    """Stand-in for ``fs_instance.fs`` — supports ``open`` and ``rm``."""

    def __init__(
        self,
        handle: FakeHandle,
        rm_side_effect: Callable[[str], None] | None = None,
    ) -> None:
        self._handle = handle
        self._rm_side_effect = rm_side_effect
        self.open_calls: list[dict[str, Any]] = []
        self.rm_calls: list[str] = []

    def open(self, path: str, mode: str, block_size: int) -> FakeHandle:
        self.open_calls.append({"path": path, "mode": mode, "block_size": block_size})
        return self._handle

    def rm(self, path: str) -> None:
        self.rm_calls.append(path)
        if self._rm_side_effect is not None:
            self._rm_side_effect(path)


class FakeStorage:
    """Stand-in for the ``FileStorage`` wrapper passed to the helper."""

    def __init__(
        self,
        handle: FakeHandle | None = None,
        write_side_effect: Callable[[str], None] | None = None,
        rm_side_effect: Callable[[str], None] | None = None,
    ) -> None:
        self.write_calls: list[dict[str, Any]] = []
        self._write_side_effect = write_side_effect
        self.fs = (
            FakeFs(handle, rm_side_effect=rm_side_effect) if handle is not None else None
        )

    def write(self, *, path: str, mode: str, data: bytes) -> None:
        self.write_calls.append({"path": path, "mode": mode, "data": data})
        if self._write_side_effect is not None:
            self._write_side_effect(path)


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


def test_bytes_input_failure_removes_file(handle: FakeHandle) -> None:
    def boom(_: str) -> None:
        raise RuntimeError("upload exploded")

    storage = FakeStorage(handle=handle, write_side_effect=boom)

    with pytest.raises(RuntimeError, match="upload exploded"):
        write_streaming(storage, "/p/file.pdf", b"abc")

    assert storage.fs.rm_calls == ["/p/file.pdf"]


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
    assert storage.fs.rm_calls == []


def test_file_like_without_chunks_falls_back_to_read(
    storage: FakeStorage, handle: FakeHandle
) -> None:
    payload = b"X" * (STREAMING_CHUNK_SIZE + 17)
    file_like = io.BytesIO(payload)

    write_streaming(storage, "/p/file.bin", file_like)

    assert b"".join(handle.writes) == payload
    assert handle.closed == 1


def test_streaming_error_removes_file(storage: FakeStorage) -> None:
    def boom(_: bytes) -> None:
        raise RuntimeError("connection reset")

    failing = FakeHandle(write_side_effect=boom)
    storage.fs = FakeFs(failing)

    with pytest.raises(RuntimeError, match="connection reset"):
        write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"abc" * 100, 8))

    assert storage.fs.rm_calls == ["/p/file.pdf"]
    assert failing.closed == 1


def test_streaming_writes_one_chunk_at_a_time_not_coalesced(
    storage: FakeStorage, handle: FakeHandle
) -> None:
    """A 4-chunk generator source must produce 4 distinct ``write`` calls of
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


def test_rm_failure_does_not_mask_original_error(
    storage: FakeStorage, caplog: pytest.LogCaptureFixture
) -> None:
    def write_boom(_: bytes) -> None:
        raise RuntimeError("primary failure")

    def rm_boom(_: str) -> None:
        raise OSError("rm denied")

    failing = FakeHandle(write_side_effect=write_boom)
    storage.fs = FakeFs(failing, rm_side_effect=rm_boom)

    with caplog.at_level(
        "WARNING", logger="utils.file_storage.helpers.streaming_writer"
    ):
        with pytest.raises(RuntimeError, match="primary failure"):
            write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 8, 4))

    assert storage.fs.rm_calls == ["/p/file.pdf"]
    assert any("cleanup rm failed" in rec.message for rec in caplog.records)


def test_rm_file_not_found_is_swallowed(storage: FakeStorage) -> None:
    """If the underlying object never materialised, ``rm`` raises
    ``FileNotFoundError`` — that's not an error worth surfacing.
    """

    def write_boom(_: bytes) -> None:
        raise RuntimeError("primary failure")

    def rm_missing(_: str) -> None:
        raise FileNotFoundError()

    failing = FakeHandle(write_side_effect=write_boom)
    storage.fs = FakeFs(failing, rm_side_effect=rm_missing)

    with pytest.raises(RuntimeError, match="primary failure"):
        write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 8, 4))

    assert storage.fs.rm_calls == ["/p/file.pdf"]


def test_non_callable_chunks_attr_uses_read_fallback(
    storage: FakeStorage, handle: FakeHandle
) -> None:
    """A non-callable ``chunks`` attribute must not be invoked — fall back
    to read-based iteration instead.
    """

    class _DataAttrChunks:
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
    """Provider multipart commits happen inside ``close()`` — a close
    failure on the success path means the upload did not finalize.
    """

    def fail_close() -> None:
        raise RuntimeError("multipart commit failed")

    failing = FakeHandle(close_side_effect=fail_close)
    storage.fs = FakeFs(failing)

    with pytest.raises(RuntimeError, match="multipart commit failed"):
        write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 8, 4))

    assert failing.closed == 1
    # close failed after a fully-written stream, so success path did not
    # invoke remove.
    assert storage.fs.rm_calls == []


def test_close_failure_after_write_error_does_not_mask_original(
    storage: FakeStorage,
) -> None:
    """When the write loop already raised, a subsequent close failure
    must be swallowed so the original exception reaches the caller intact.
    """

    def fail_write(_: bytes) -> None:
        raise RuntimeError("primary write failure")

    def fail_close() -> None:
        raise RuntimeError("secondary close failure")

    failing = FakeHandle(write_side_effect=fail_write, close_side_effect=fail_close)
    storage.fs = FakeFs(failing)

    with pytest.raises(RuntimeError, match="primary write failure"):
        write_streaming(storage, "/p/file.pdf", UploadedFileLike(b"X" * 8, 4))

    assert failing.closed == 1
    assert storage.fs.rm_calls == ["/p/file.pdf"]
