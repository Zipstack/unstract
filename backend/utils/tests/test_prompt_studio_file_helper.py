"""Tests for the streaming write helper and the IDE file delete."""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import pytest

from utils.file_storage.helpers.streaming_writer import (
    STREAMING_CHUNK_SIZE,
    write_streaming,
)


class FakeHandle:
    """Stand-in for an fsspec file handle. Records writes; lets tests
    inject failures via ``write_side_effect`` / ``close_side_effect``.
    """

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

    assert storage.write_calls == [{"path": "/p/file.pdf", "mode": "wb", "data": b"abc"}]
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

    with caplog.at_level("WARNING", logger="utils.file_storage.helpers.streaming_writer"):
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


# --- delete_for_ide: idempotent on the source file ------------------------
#
# Callers delete the object-store file *before* the DocumentManager row, so a
# failed file delete leaves a row worth retrying. The residue in the other
# direction — file gone, row delete failed — then retries against a path that
# is no longer there. An unguarded rm() raises FileNotFoundError on the usual
# fsspec backends, the view's broad except turns that into "File deletion
# failed" (400), and the row can never be deleted through the endpoint again.


class _DeleteFs:
    """Minimal fsspec stand-in: rm() raises on a path that is not there."""

    def __init__(self, existing: list[str]) -> None:
        self.existing = set(existing)
        self.removed: list[str] = []

    def exists(self, path: str) -> bool:
        return path in self.existing

    def rm_exact(self, path: str) -> None:
        if path not in self.existing:
            raise FileNotFoundError(path)
        self.existing.remove(path)
        self.removed.append(path)

    def rm(self, path: str, recursive: bool = True) -> None:
        # Paths here carry the document's name; rm() would glob it on GCS/S3.
        raise AssertionError(f"delete_for_ide must use rm_exact, not rm: {path}")

    def glob(self, pattern: str) -> list[str]:
        return []


def _delete_with(fs: _DeleteFs, file_name: str = "invoice.pdf", base: str = "/base"):
    from unittest.mock import patch

    from utils.file_storage.helpers.prompt_studio_file_helper import (
        PromptStudioFileHelper,
    )

    module = "utils.file_storage.helpers.prompt_studio_file_helper"
    with (
        patch(f"{module}.EnvHelper.get_storage", return_value=fs),
        patch.object(
            PromptStudioFileHelper,
            "get_or_create_prompt_studio_subdirectory",
            return_value=base,
        ),
    ):
        return PromptStudioFileHelper.delete_for_ide(
            org_id="org", user_id="user", tool_id="tool", file_name=file_name
        )


def test_delete_for_ide_removes_the_source_file() -> None:
    """Without this, a guard that skipped everything would pass below."""
    fs = _DeleteFs(["/base/invoice.pdf"])

    assert _delete_with(fs) is True
    assert fs.removed == ["/base/invoice.pdf"]


def test_delete_for_ide_is_idempotent_when_the_source_is_already_gone() -> None:
    """The retry after a partial failure has to be able to reach the row."""
    fs = _DeleteFs([])

    assert _delete_with(fs) is True
    assert fs.removed == []


# --- delete_for_ide: names with glob characters ---------------------------
#
# The document's name is part of every path deleted here. fsspec reads
# "[Final]" as a character class: on GCS/S3 rm("Report [Final].pdf") misses
# itself and deletes "Report F.pdf" instead (seen on MinIO), and the related
# files glob matched the wrong document's extract files the same way.


def test_delete_for_ide_leaves_a_glob_matching_document_alone(tmp_path) -> None:  # noqa: ANN001
    from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

    storage = FileStorage(provider=FileStorageProvider.LOCAL)
    for rel in (
        "Report [Final].pdf",
        "extract/Report [Final].txt",
        "extract/metadata/Report [Final].json",
        "Report F.pdf",  # what "[Final]" matches as a glob
        "extract/Report F.txt",
        "extract/metadata/Report F.json",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"x")

    assert _delete_with(storage, "Report [Final].pdf", str(tmp_path)) is True

    left = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*.*"))
    assert left == [
        "Report F.pdf",
        "extract/Report F.txt",
        "extract/metadata/Report F.json",
    ]
