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
boot the full Django settings chain via the calling helper.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest

from utils.file_storage.helpers.streaming_writer import (
    STREAMING_CHUNK_SIZE,
    write_streaming,
)


@pytest.fixture
def mock_storage() -> tuple[MagicMock, MagicMock]:
    """Return (fs_instance_mock, raw_fs_handle_mock).

    The helper interacts with both: ``fs_instance.write`` for the bytes
    fast-path and ``fs_instance.fs.open`` for streaming.
    """
    raw_fs = MagicMock()
    storage = MagicMock()
    storage.fs = raw_fs
    return storage, raw_fs


def _open_returns(raw_fs: MagicMock, sink: io.BytesIO) -> MagicMock:
    """Wire the mocked fsspec handle so its ``open()`` returns a writable
    object that records bytes into ``sink`` and exposes ``abort_mpu``.
    """
    handle = MagicMock()
    handle.write.side_effect = sink.write
    handle.close = MagicMock()
    raw_fs.open.return_value = handle
    return handle


class _UploadedFileLike:
    """Mimics ``django.core.files.uploadedfile.UploadedFile.chunks``."""

    def __init__(self, payload: bytes, chunk_size: int):
        self._payload = payload
        self._chunk_size = chunk_size
        self.chunks_called_with: int | None = None

    def chunks(self, chunk_size: int = 64 * 1024):
        self.chunks_called_with = chunk_size
        for i in range(0, len(self._payload), chunk_size):
            yield self._payload[i : i + chunk_size]


class TestWriteStreaming:
    def test_bytes_input_uses_single_shot_write(
        self, mock_storage: tuple[MagicMock, MagicMock]
    ) -> None:
        storage, raw_fs = mock_storage

        write_streaming(storage, "/p/file.pdf", b"abc")

        storage.write.assert_called_once_with(path="/p/file.pdf", mode="wb", data=b"abc")
        raw_fs.open.assert_not_called()

    def test_uploaded_file_streams_via_chunks(
        self, mock_storage: tuple[MagicMock, MagicMock]
    ) -> None:
        storage, raw_fs = mock_storage
        sink = io.BytesIO()
        _open_returns(raw_fs, sink)
        payload = b"PDFBYTES" * 10_000
        upload = _UploadedFileLike(payload, chunk_size=STREAMING_CHUNK_SIZE)

        write_streaming(storage, "/p/file.pdf", upload)

        # Provider-native multipart hint propagated.
        raw_fs.open.assert_called_once_with(
            "/p/file.pdf", mode="wb", block_size=STREAMING_CHUNK_SIZE
        )
        assert sink.getvalue() == payload
        assert upload.chunks_called_with == STREAMING_CHUNK_SIZE
        # Bytes branch must NOT have been used.
        storage.write.assert_not_called()

    def test_file_like_without_chunks_falls_back_to_read(
        self, mock_storage: tuple[MagicMock, MagicMock]
    ) -> None:
        storage, raw_fs = mock_storage
        sink = io.BytesIO()
        _open_returns(raw_fs, sink)
        payload = b"X" * (STREAMING_CHUNK_SIZE + 17)
        # Plain BytesIO has no .chunks() — exercises the read() fallback.
        file_like = io.BytesIO(payload)

        write_streaming(storage, "/p/file.bin", file_like)

        assert sink.getvalue() == payload

    def test_streaming_error_triggers_abort_mpu(
        self, mock_storage: tuple[MagicMock, MagicMock]
    ) -> None:
        storage, raw_fs = mock_storage
        handle = MagicMock()
        handle.write.side_effect = RuntimeError("connection reset")
        handle.abort_mpu = MagicMock()
        raw_fs.open.return_value = handle
        upload = _UploadedFileLike(b"abc" * 100, chunk_size=8)

        with pytest.raises(RuntimeError, match="connection reset"):
            write_streaming(storage, "/p/file.pdf", upload)

        handle.abort_mpu.assert_called_once()
        handle.close.assert_called_once()

    def test_streaming_error_falls_back_to_discard_when_no_abort_mpu(
        self, mock_storage: tuple[MagicMock, MagicMock]
    ) -> None:
        storage, raw_fs = mock_storage
        handle = MagicMock(spec=["write", "close", "discard"])
        handle.write.side_effect = RuntimeError("broken pipe")
        raw_fs.open.return_value = handle

        with pytest.raises(RuntimeError, match="broken pipe"):
            write_streaming(storage, "/p/file.pdf", _UploadedFileLike(b"X" * 32, 8))

        handle.discard.assert_called_once()
        handle.close.assert_called_once()

    def test_streaming_writes_one_chunk_at_a_time_not_coalesced(
        self, mock_storage: tuple[MagicMock, MagicMock]
    ) -> None:
        """Catches the 'collapse chunks into one bytes blob' regression.

        A 4-chunk generator source must produce 4 distinct ``write`` calls
        of ``<= chunk_size`` each — proves the helper isn't accumulating
        in a single buffer before flushing.
        """
        storage, raw_fs = mock_storage
        chunk_sizes: list[int] = []
        handle = MagicMock()
        handle.write.side_effect = lambda chunk: chunk_sizes.append(len(chunk))
        raw_fs.open.return_value = handle

        class _GenSource:
            """Streaming source with chunks() returning a fresh generator —
            no backing buffer, mimics django's temp-file-backed upload."""

            def chunks(self, chunk_size: int = 64 * 1024):
                for _ in range(4):
                    yield b"Z" * STREAMING_CHUNK_SIZE

        write_streaming(storage, "/p/big.pdf", _GenSource())

        assert len(chunk_sizes) == 4
        assert all(size <= STREAMING_CHUNK_SIZE for size in chunk_sizes)


# Integration smoke (wiring upload_for_ide → write_streaming) is not
# unit-testable without booting Django settings (the helper transitively
# imports file_management → backend.__init__ → celery → settings). The
# call-site is a one-line delegation; coverage of the streaming behaviour
# above is sufficient. End-to-end behaviour is verified via the SDK
# migration smoke run on a real stack.
