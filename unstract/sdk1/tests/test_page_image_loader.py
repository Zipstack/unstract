"""Tests for the FileStorage-backed page-image loader (reader side).

Covers discovery + natural ordering (incl. >999 pages), the page cap,
base64 encoding and vision message-block construction, and the typed
empty/partial/duplicate failure modes — across the in-memory S3-like
double and the real local-filesystem FileStorage backend.
"""

import base64
from pathlib import Path

import pytest
from llmw_image_fixtures import InMemoryFileStorage, minimal_png
from unstract.sdk1.adapters.x2text.page_image_loader import (
    DEFAULT_PAGE_CAP,
    LoadedPageImage,
    PageCapExceededError,
    PageImageSetIncompleteError,
    PageImagesNotFoundError,
    build_vision_message_content,
    discover_page_images,
    load_page_images,
)
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

_DIR = "/data/extract/doc/pages"


def _store(
    pages: dict[int, bytes], extra: dict[str, bytes] | None = None
) -> InMemoryFileStorage:
    fs = InMemoryFileStorage()
    for number, data in pages.items():
        fs.write(path=f"{_DIR}/page_{number:03d}.png", mode="wb", data=data)
    for name, data in (extra or {}).items():
        fs.write(path=f"{_DIR}/{name}", mode="wb", data=data)
    return fs


class TestDiscovery:
    def test_orders_by_integer_page_number(self) -> None:
        fs = _store({n: b"x" for n in (3, 1, 2)})
        assert [n for n, _ in discover_page_images(fs, _DIR)] == [1, 2, 3]

    def test_returns_full_paths(self) -> None:
        fs = _store({1: b"x"})
        assert discover_page_images(fs, _DIR) == [(1, f"{_DIR}/page_001.png")]

    def test_natural_sort_beyond_999_pages(self) -> None:
        # Lexicographic ordering would put page_1000 before page_999.
        fs = InMemoryFileStorage()
        for n in (999, 1000, 1, 1001):
            fs.write(path=f"{_DIR}/page_{n:03d}.png", mode="wb", data=b"x")
        # Fill 2..998 so the set is contiguous.
        for n in range(2, 999):
            fs.write(path=f"{_DIR}/page_{n:03d}.png", mode="wb", data=b"x")
        numbers = [n for n, _ in discover_page_images(fs, _DIR)]
        assert numbers == list(range(1, 1002))

    def test_ignores_non_page_entries(self) -> None:
        fs = _store({1: b"x", 2: b"y"}, extra={"thumbnail.png": b"t", "notes.txt": b"n"})
        assert [n for n, _ in discover_page_images(fs, _DIR)] == [1, 2]


class TestFailureModes:
    def test_missing_directory_raises_not_found(self) -> None:
        with pytest.raises(PageImagesNotFoundError) as excinfo:
            discover_page_images(InMemoryFileStorage(), _DIR)
        # Remediation must steer to cache-bypass re-extraction + billing note.
        assert "cache bypass" in str(excinfo.value)
        assert "billed per page" in str(excinfo.value)

    def test_directory_with_only_foreign_files_raises_not_found(self) -> None:
        fs = _store({}, extra={"thumbnail.png": b"t"})
        with pytest.raises(PageImagesNotFoundError):
            discover_page_images(fs, _DIR)

    def test_partial_set_raises_incomplete_with_missing_pages(self) -> None:
        fs = _store({1: b"a", 2: b"b", 4: b"d", 7: b"g"})
        with pytest.raises(PageImageSetIncompleteError) as excinfo:
            discover_page_images(fs, _DIR)
        err = excinfo.value
        assert err.found_pages == [1, 2, 4, 7]
        assert err.missing_pages == [3, 5, 6]
        assert "cache bypass" in str(err)

    def test_empty_and_partial_are_distinct_types(self) -> None:
        # Callers branch remediation copy on the exception type; neither may
        # be a subclass of the other.
        assert not issubclass(PageImagesNotFoundError, PageImageSetIncompleteError)
        assert not issubclass(PageImageSetIncompleteError, PageImagesNotFoundError)

    def test_duplicate_page_numbers_raise_incomplete(self) -> None:
        fs = _store({1: b"a"})
        # page_001.png and page_1.png parse to the same page number.
        fs.write(path=f"{_DIR}/page_1.png", mode="wb", data=b"dup")
        with pytest.raises(PageImageSetIncompleteError, match="Duplicate"):
            discover_page_images(fs, _DIR)


class TestPageCap:
    def test_within_cap_loads(self) -> None:
        fs = _store({1: b"a", 2: b"b"})
        assert len(load_page_images(fs, _DIR, page_cap=2)) == 2

    def test_over_cap_raises_with_clear_message(self) -> None:
        fs = _store({n: b"x" for n in range(1, 6)})
        with pytest.raises(PageCapExceededError) as excinfo:
            load_page_images(fs, _DIR, page_cap=4)
        err = excinfo.value
        assert err.page_count == 5
        assert err.page_cap == 4
        assert "exceeds 4 pages" in str(err)

    def test_cap_check_precedes_reads(self) -> None:
        # Fail-fast: no image bytes are read for an oversized document.
        fs = _store({n: b"x" for n in range(1, 6)})
        reads: list[str] = []
        original_read = fs.read
        fs.read = lambda path, **kw: reads.append(path) or original_read(path, **kw)
        with pytest.raises(PageCapExceededError):
            load_page_images(fs, _DIR, page_cap=1)
        assert reads == []

    def test_none_disables_cap(self) -> None:
        fs = _store({n: b"x" for n in range(1, DEFAULT_PAGE_CAP + 5)})
        loaded = load_page_images(fs, _DIR, page_cap=None)
        assert len(loaded) == DEFAULT_PAGE_CAP + 4


class TestLoadingAndEncoding:
    def test_base64_round_trip(self) -> None:
        payload = minimal_png()
        fs = _store({1: payload})
        [loaded] = load_page_images(fs, _DIR)
        assert isinstance(loaded, LoadedPageImage)
        assert base64.b64decode(loaded.base64_data) == payload

    def test_loaded_pages_keep_page_order(self) -> None:
        fs = _store({2: b"two", 1: b"one", 3: b"three"})
        loaded = load_page_images(fs, _DIR)
        assert [p.page_number for p in loaded] == [1, 2, 3]
        assert base64.b64decode(loaded[0].base64_data) == b"one"


class TestVisionMessageContent:
    def test_prompt_first_then_labelled_pages(self) -> None:
        pages = [
            LoadedPageImage(page_number=1, path="p1", base64_data="QQ=="),
            LoadedPageImage(page_number=2, path="p2", base64_data="Qg=="),
        ]
        content = build_vision_message_content(pages, "What is the total?")
        assert content[0] == {"type": "text", "text": "What is the total?"}
        # "Page N" label immediately precedes each image, in page order.
        assert content[1] == {"type": "text", "text": "Page 1"}
        assert content[2]["type"] == "image_url"
        assert content[2]["image_url"]["url"] == "data:image/png;base64,QQ=="
        assert content[3] == {"type": "text", "text": "Page 2"}
        assert content[4]["image_url"]["url"] == "data:image/png;base64,Qg=="
        assert len(content) == 5

    def test_no_pages_yields_prompt_only(self) -> None:
        assert build_vision_message_content([], "q") == [{"type": "text", "text": "q"}]


class TestLocalFileStorageBackend:
    """UNS-809: the loader behaves identically on a real FileStorage backend."""

    def _local_fs(self) -> FileStorage:
        return FileStorage(provider=FileStorageProvider.LOCAL)

    def test_discovery_and_load_on_local_backend(self, tmp_path: Path) -> None:
        fs = self._local_fs()
        pages_dir = str(tmp_path / "doc" / "pages")
        fs.mkdir(pages_dir)
        payloads = {1: b"one", 2: b"two", 10: b"ten"}
        for n in range(1, 11):
            fs.write(
                path=f"{pages_dir}/page_{n:03d}.png",
                mode="wb",
                data=payloads.get(n, b"x"),
            )
        loaded = load_page_images(fs, pages_dir, page_cap=None)
        assert [p.page_number for p in loaded] == list(range(1, 11))
        assert base64.b64decode(loaded[9].base64_data) == b"ten"

    def test_missing_dir_on_local_backend(self, tmp_path: Path) -> None:
        with pytest.raises(PageImagesNotFoundError):
            discover_page_images(self._local_fs(), str(tmp_path / "absent" / "pages"))

    def test_partial_set_on_local_backend(self, tmp_path: Path) -> None:
        fs = self._local_fs()
        pages_dir = str(tmp_path / "doc" / "pages")
        fs.mkdir(pages_dir)
        for n in (1, 3):
            fs.write(path=f"{pages_dir}/page_{n:03d}.png", mode="wb", data=b"x")
        with pytest.raises(PageImageSetIncompleteError) as excinfo:
            discover_page_images(fs, pages_dir)
        assert excinfo.value.missing_pages == [2]
