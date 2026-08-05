"""Shared test fixtures and stubs for LLMWhisperer image output mode (UNS-762).

Importable from multiple test modules::

    from tests.llmw_image_fixtures import (
        make_page_zip,
        CORRUPT_ZIP,
        minimal_png,
        InMemoryFileStorage,
        FlakyFileStorage,
    )

Provides:
- A happy-path ZIP builder producing ``page_00N.png`` entries with valid PNGs.
- Corrupt / non-ZIP byte fixtures for error-path testing.
- In-memory ``FileStorage`` doubles (S3-like) needing no network/credentials.
"""

from __future__ import annotations

import binascii
import io
import struct
import zipfile
import zlib

from unstract.sdk1.exceptions import FileOperationError
from unstract.sdk1.file_storage import FileStorageProvider


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = binascii.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def minimal_png() -> bytes:
    """Return the bytes of a valid 1x1 RGB PNG."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit RGB
    raw = b"\x00\xff\x00\x00"  # one scanline: filter byte 0 + red pixel
    idat = zlib.compress(raw)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def make_page_zip(
    num_pages: int, *, padding: int = 3, ext: str = ".png", shuffle: bool = False
) -> bytes:
    """Build a ZIP of ``page_00N.png`` entries (valid PNGs).

    Args:
        num_pages: Number of page images to include.
        padding: Zero-padding width for the page number.
        ext: File extension for each page entry.
        shuffle: If True, write entries in reverse order (to prove the
            extractor sorts, not relies on archive order).
    """
    order = range(num_pages, 0, -1) if shuffle else range(1, num_pages + 1)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for i in order:
            archive.writestr(f"page_{str(i).zfill(padding)}{ext}", minimal_png())
    return buffer.getvalue()


# A byte sequence that is not a valid ZIP archive.
CORRUPT_ZIP = b"this is definitely not a zip archive"


class InMemoryFileStorage:
    """Minimal in-memory FileStorage double (S3-like), no network/credentials.

    Implements only the surface the image-mode helper uses: ``provider``,
    ``mkdir``, ``write``, ``read``, ``exists``.
    """

    def __init__(self, provider: FileStorageProvider = FileStorageProvider.S3) -> None:
        """Create an empty in-memory store for the given provider."""
        self.provider = provider
        self._files: dict[str, bytes] = {}
        self._dirs: set[str] = set()
        self.write_calls = 0
        self.rm_calls: list[str] = []

    def rm(self, path: str, recursive: bool = True) -> None:
        self.rm_calls.append(str(path))
        prefix = str(path).rstrip("/") + "/"
        for key in list(self._files):
            if key == str(path) or key.startswith(prefix):
                del self._files[key]

    def mkdir(self, path: str, create_parents: bool = True) -> None:
        self._dirs.add(str(path))

    def write(
        self,
        path: str,
        mode: str = "wb",
        encoding: str = "utf-8",
        data: bytes | str = b"",
        **_: object,
    ) -> int:
        self.write_calls += 1
        payload = data.encode(encoding) if isinstance(data, str) else bytes(data)
        self._files[str(path)] = payload
        return len(payload)

    def read(
        self,
        path: str,
        mode: str = "rb",
        encoding: str = "utf-8",
        length: int = -1,
        **_: object,
    ) -> bytes | str:
        try:
            payload = self._files[str(path)]
        except KeyError:
            # Real backends (fsspec/local) raise FileNotFoundError.
            raise FileNotFoundError(str(path)) from None
        if length is not None and length >= 0:
            payload = payload[:length]
        return payload if "b" in mode else payload.decode(encoding)

    def exists(self, path: str) -> bool:
        key = str(path)
        if key in self._files or key in self._dirs:
            return True
        # S3-like: a "directory" exists when any object lives under it.
        prefix = key.rstrip("/") + "/"
        return any(stored.startswith(prefix) for stored in self._files)

    def size(self, path: str) -> int:
        """Byte size from 'metadata' (fsspec info-style), like real backends."""
        try:
            return len(self._files[str(path)])
        except KeyError:
            raise FileNotFoundError(str(path)) from None

    def ls(self, path: str) -> list[str]:
        """Direct children of ``path`` (full paths), fsspec-style."""
        from pathlib import PurePosixPath

        parent = str(path).rstrip("/")
        return sorted(
            stored
            for stored in self._files
            if str(PurePosixPath(stored).parent) == parent
        )

    @property
    def stored_paths(self) -> list[str]:
        return sorted(self._files)


class FlakyFileStorage(InMemoryFileStorage):
    """In-memory double whose writes fail a configurable number of times.

    Used to exercise the per-page write retry loop and the fail-closed policy.
    """

    def __init__(
        self,
        fail_times: int = 1,
        fail_always: bool = False,
        fail_substrings: tuple[str, ...] = (),
        **kwargs: object,
    ) -> None:
        """Configure how many writes per path fail before succeeding.

        ``fail_substrings`` always-fails any write whose path contains one of
        the substrings — used to fail a specific page (mid-list failure).
        """
        super().__init__(**kwargs)
        self.fail_times = fail_times
        self.fail_always = fail_always
        self.fail_substrings = tuple(fail_substrings)
        self._attempts: dict[str, int] = {}

    def write(
        self,
        path: str,
        mode: str = "wb",
        encoding: str = "utf-8",
        data: bytes | str = b"",
        **kwargs: object,
    ) -> int:
        key = str(path)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        always_fail = self.fail_always or any(s in key for s in self.fail_substrings)
        if always_fail or self._attempts[key] <= self.fail_times:
            raise FileOperationError(f"simulated write failure for {key}")
        return super().write(path, mode, encoding, data, **kwargs)

    def attempts_for(self, path: str) -> int:
        return self._attempts.get(str(path), 0)
